#!/usr/bin/env python3
"""Replay converted traces through the machine in fsm.yaml.

Input is calls.jsonl from convert.py -- typed operations with absolute paths. The
checker never sees a shell string, a tmux escape or an agent's output. That is the
whole point of the three-layer split: a finding here can be wrong about the FILESYSTEM
but cannot be wrong about what the terminal rendered.

    state   (trace, path) -> UNKNOWN | EXISTS | ABSENT
    ledger  paths the agent had a legitimate source for

Both are needed because they separate two failures that look identical if you track
only states, exactly as in mr/typestate.py:

    UNBOUND_IDENTIFIER    the path appears in no ledger -- an invented filename
    UNDEFINED_TRANSITION  the path is real but was removed -- use after delete

Calls are skipped, never guessed at, when the path is null (unresolved argument or no
path operand) or falls outside the judged scope.

Run:
    python3 fs_typestate.py --calls calls.jsonl
    python3 fs_typestate.py --calls calls.jsonl --task decommissioning-service-with-sensitive-data
    python3 fs_typestate.py --calls calls.jsonl --jsonl findings.jsonl
"""

from __future__ import annotations

import argparse
import collections
import json
import posixpath
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import convert as C  # noqa: E402  (seed_ledger, workdir_for)
import fs_trace as F  # noqa: E402  (in_scope)


class Kind(StrEnum):
    UNBOUND_IDENTIFIER = "UNBOUND_IDENTIFIER"
    UNDEFINED_TRANSITION = "UNDEFINED_TRANSITION"
    GUARD_UNSATISFIED = "GUARD_UNSATISFIED"


@dataclass
class Finding:
    kind: Kind
    op: str
    resource: str
    path: str
    observed_state: str
    expected_states: list[str]
    trace: str
    task: str
    step: int
    raw: str
    rule: str
    detail: str
    after_opaque_exec: bool
    # How much of the trace preceding this call the machine could not follow. A finding
    # raised after many blind calls deserves less trust, and saying so is cheaper than
    # pretending the number is not there.
    blind_calls_before: int

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["kind"] = str(self.kind)
        return d


@dataclass
class Machine:
    states: list[str]
    initial: str
    edges: dict[str, list[dict]]
    judged: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> Machine:
        spec = yaml.safe_load(path.read_text())
        initial = next(s for s, v in spec["states"].items() if (v or {}).get("initial"))
        return cls(
            states=list(spec["states"]),
            initial=initial,
            edges=spec["edges"],
            judged=tuple(spec["scope"]["judged"]),
        )


@dataclass
class Ledger:
    """Paths with a legitimate source, plus directories whose whole subtree counts.

    The subtree rule is how the ledger grows without parsing any output: after a
    listing the adapter cannot know which names came back, so it admits everything
    under that directory. Loose in the direction of missing invented paths, never in
    the direction of inventing accusations.
    """

    exact: set[str] = field(default_factory=set)
    subtrees: set[str] = field(default_factory=set)

    def add(self, p: str) -> None:
        self.exact.add(p)

    def add_subtree(self, p: str) -> None:
        self.subtrees.add(p)
        self.exact.add(p)

    def __contains__(self, p: str) -> bool:
        if p in self.exact:
            return True
        return any(p == d or p.startswith(d.rstrip("/") + "/") for d in self.subtrees)


def _paths_for(edge: dict, args: dict) -> list[str | None]:
    """Which argument does this edge's `resource` name?"""
    r = edge.get("resource")
    if r == "member":
        return list(args.get("members") or [])
    if r in ("path", "src", "dst", "archive"):
        return [args.get(r)]
    return []


class Checker:
    def __init__(self, machine: Machine):
        self.m = machine

    def run(self, calls: list[dict], seed: set[str], cwd: str,
            exists: set[str] | None = None) -> tuple[list[Finding], dict]:
        state: dict[str, str] = {}
        ledger = Ledger()
        # Knowing a name and the file being there are different claims, and only the
        # Dockerfile supports the second one.
        for p in seed:
            ledger.add(p)
        for p in exists or ():
            ledger.add(p)
            state[p] = "EXISTS"
        ledger.add_subtree(cwd)  # the agent can see its own working directory

        found: list[Finding] = []
        stats: collections.Counter = collections.Counter()
        after_opaque = False
        blind = 0

        for call in calls:
            op = call["op"]
            args = call.get("args") or {}
            edges = self.m.edges.get(op) or []
            if op in ("sys.opaque",):
                after_opaque = True
                blind += 1
                stats["blind_opaque"] += 1
                continue
            if op == "sys.noop":
                continue
            if args.get("unresolved") or call.get("no_path_operand"):
                blind += 1
                stats["blind_unresolved" if args.get("unresolved") else "blind_no_operand"] += 1
                continue

            for edge in edges:
                if not edge.get("resource") or edge["resource"] == "none":
                    continue
                for path in _paths_for(edge, args):
                    if not path:
                        continue
                    if not F.in_scope(path):
                        stats["out_of_scope"] += 1
                        continue
                    stats["checked"] += 1
                    f = self._step(edge, op, path, call, state, ledger, after_opaque, blind)
                    if f is not None:
                        found.append(f)
                        stats[str(f.kind)] += 1
            if op == "fs.exec":
                after_opaque = True
                blind += 1
                stats["blind_exec"] += 1
        return found, stats

    def _step(self, edge, op, path, call, state, ledger, after_opaque, blind) -> Finding | None:
        st = state.get(path, self.m.initial)
        src = edge.get("src") or []
        guard = edge.get("guard") or ""

        def mk(kind: Kind, detail: str) -> Finding:
            return Finding(
                kind=kind, op=op, resource=edge["resource"], path=path,
                observed_state=st, expected_states=list(src),
                trace=call["trace"], task=call["task"], step=call["step"],
                raw=call["raw"], rule=call.get("rule", ""), detail=detail,
                after_opaque_exec=after_opaque, blind_calls_before=blind,
            )

        finding: Finding | None = None

        # An invented filename and a removed one are one mistake each, never both:
        # report the ledger failure and stop, as typestate.py does.
        if "in ledger" in guard and path not in ledger:
            finding = mk(Kind.UNBOUND_IDENTIFIER,
                         f"{path} was never named by the task, created by the trace, "
                         f"or seen under a listed directory")
        elif st in (edge.get("violation_if_src") or []):
            finding = mk(Kind.UNDEFINED_TRANSITION,
                         f"{op} is defined on {'|'.join(src)}; {path} is {st}")
        elif "parent" in guard:
            parent = posixpath.dirname(path)
            if state.get(parent) == "ABSENT":
                finding = mk(Kind.GUARD_UNSATISFIED,
                             f"parent {parent} is ABSENT")

        self._apply(edge, op, path, call, state, ledger)
        return finding

    # 126 = found but not executable, 127 = not found. Both describe the BINARY, not
    # the path it was given, so they must not be read as "the path is absent". This
    # corpus is full of them: containers ship without xxd, file, od.
    TOOL_MISSING = (126, 127)

    def _apply(self, edge, op, path, call, state, ledger) -> None:
        dst = edge.get("dst")
        rc = call.get("exit_code")
        attributable = bool(call.get("exit_code_attributable")) and rc is not None
        failed = attributable and rc != 0
        if dst == "from_exit_code":
            # fs.stat and fs.list. A step joined by && or || carries one exit code for
            # the whole step, so the result cannot be attributed and the state stands.
            if attributable and rc not in self.TOOL_MISSING:
                state[path] = "EXISTS" if rc == 0 else "ABSENT"
            ledger.add(path)
            # An enumeration admits its whole subtree regardless of how the state
            # resolved: the ledger asks "could the agent have learned this name",
            # which a listing answers even when the checker cannot read the answer.
            if op == "fs.list":
                ledger.add_subtree(path)
            return
        if dst in (None, "unchanged"):
            return
        if failed:
            # A call that failed leaves the resource where it was -- the same rule as
            # mr/typestate.py. Known imprecision: a shell redirection creates its
            # target BEFORE the command runs, so `missingcmd > f` does leave an empty
            # f behind even at rc=127. Treating it as unchanged under-reports.
            return
        state[path] = dst
        if dst == "EXISTS":
            ledger.add(path)
            if op == "fs.list":
                ledger.add_subtree(path)
        elif dst == "ABSENT" and (call.get("args") or {}).get("recursive"):
            for p in list(state):
                if p.startswith(path.rstrip("/") + "/"):
                    state[p] = "ABSENT"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--calls", type=Path, default=HERE / "calls.jsonl")
    ap.add_argument("--fsm", type=Path, default=HERE / "fsm.yaml")
    ap.add_argument("--task")
    ap.add_argument("--jsonl", type=Path)
    ap.add_argument("--show", type=int, default=10)
    a = ap.parse_args()

    machine = Machine.load(a.fsm)
    checker = Checker(machine)

    by_trace: dict[str, list[dict]] = collections.defaultdict(list)
    for line in a.calls.open():
        r = json.loads(line)
        if a.task and r["task"] != a.task:
            continue
        by_trace[r["trace"]].append(r)

    findings: list[Finding] = []
    stats: collections.Counter = collections.Counter()
    dirty = 0
    for trace, calls in by_trace.items():
        task = calls[0]["task"]
        fs, st = checker.run(calls, C.seed_ledger(task), C.workdir_for(task),
                             C.seed_exists(task))
        findings.extend(fs)
        stats.update(st)
        if fs:
            dirty += 1

    print(f"traces {len(by_trace)}  calls {sum(len(v) for v in by_trace.values())}")
    print(f"checked transitions {stats['checked']}   out of scope {stats['out_of_scope']}")
    print(f"skipped as blind:  opaque {stats['blind_opaque']}  exec {stats['blind_exec']}  "
          f"unresolved {stats['blind_unresolved']}  no-operand {stats['blind_no_operand']}")
    print(f"\ntraces with >=1 finding: {dirty}/{len(by_trace)} "
          f"({100 * dirty / max(len(by_trace), 1):.1f}%)")
    print(f"findings {len(findings)}")
    for k in Kind:
        if stats[str(k)]:
            print(f"   {stats[str(k)]:6d}  {k}")

    clean = [f for f in findings if not f.after_opaque_exec]
    print(f"\nof those, raised BEFORE any opaque call: {len(clean)} "
          f"({100 * len(clean) / max(len(findings), 1):.0f}%) -- the higher-confidence set")

    by_task = collections.Counter(f.task for f in findings)
    if by_task:
        print("\ntop tasks")
        for t, n in by_task.most_common(8):
            print(f"   {n:5d}  {t}")

    shown = (clean or findings)[: a.show]
    if shown:
        print(f"\n{len(shown)} examples")
        for f in shown:
            print(f"  [{f.kind}] {f.task} step {f.step}  op={f.op} resource={f.resource}")
            print(f"      path={f.path}  state={f.observed_state} expected={f.expected_states}")
            print(f"      raw: {f.raw[:110]}")
            print(f"      {f.detail}")
            print(f"      after_opaque_exec={f.after_opaque_exec} blind_before={f.blind_calls_before}")

    if a.jsonl:
        with a.jsonl.open("w") as fh:
            for f in findings:
                fh.write(json.dumps(f.as_dict(), ensure_ascii=False) + "\n")
        print(f"\nwrote {len(findings)} findings to {a.jsonl}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
