#!/usr/bin/env python3
"""Convert recorded agent traces into calls against the service in openapi.yaml.

AUTOMATED, NOT HAND-WRITTEN. 333 traces and 4200 steps cannot be converted by hand,
and a hand conversion would not be auditable anyway -- you could not tell a judgement
call from a typo. Instead every emitted call carries the evidence for itself:

    raw      the segment text the call came from, verbatim
    rule     which mapping rule fired
    cwd      the working directory in force when the path was resolved
    step     the index of the agent step, so it can be found in the .cast

So the conversion is machine-produced but line-by-line checkable. Anything the adapter
could not classify becomes sys.opaque with the raw text preserved -- nothing is
dropped, and the output is a total function of the input.

HOW THE AWKWARD CASES ARE HANDLED
---------------------------------
Relative paths. A path not starting with `/` is joined to the current working
directory and normalised. cwd starts at the task's Dockerfile WORKDIR when one is
declared (142 of the 151 that declare it say /app) and at /app otherwise. It then
moves only through fs.chdir. So `cd tests && touch out.txt` from /app emits
fs.chdir(/app/tests) then fs.write(/app/tests/out.txt).

`&&` and `;`. Split into separate segments and walked left to right, threading cwd.
Both are treated as plain sequencing. For `&&` that is right whenever the left side
succeeded, and a step that failed carries a nonzero exit code the reader records.

`||`. Also split and BOTH sides walked, which is wrong -- only one branch of `a || b`
runs. Choosing needs a per-segment exit code, and a trace carries one exit code per
step. Walking both over-applies writes and under-applies nothing, so the error is in
the conservative direction for reads. Declared, not fixed.

`|`. Split, but a fs.chdir inside a pipeline is marked durable:false and does not move
cwd, because it runs in a subshell. `cd d | cat x` reads /app/x, not /app/d/x.

`( ... )`. Parentheses are stripped and counted, and cwd is saved on `(` and restored
on `)`, so `(cd /tmp && touch z); touch w` emits fs.write(/tmp/z) then fs.write(/app/w).

$VAR, globs, `$(...)`. Not expanded. The call is emitted with unresolved:true and a
null path; the state machine skips it. 252 of 3369 typed calls over the leaderboard
traces.

Run:
    python3 convert.py --root ../datasets/tb-leaderboard --out calls.jsonl
    python3 convert.py --root ... --task decommissioning-service-with-sensitive-data
"""

from __future__ import annotations

import argparse
import collections
import json
import posixpath
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fs_trace as F  # noqa: E402

TASKS = Path(__file__).resolve().parent.parent / "datasets" / "terminal-bench" / "original-tasks"

# Adapter action -> operationId. fs.copy / fs.move are recombined below, because
# fs_trace emits them already decomposed.
OP = {
    F.READ: "fs.read",
    F.CREATE: "fs.write",
    F.DELETE: "fs.delete",
    F.STAT: "fs.stat",
    F.LIST: "fs.list",
    F.EXEC: "fs.exec",
    F.CHDIR: "fs.chdir",
}


def workdir_for(task: str) -> str:
    """Seed cwd from the task's Dockerfile rather than assuming /app.

    151 of 241 terminal-bench Dockerfiles declare WORKDIR; 142 of those say /app, but
    the rest say /root, /workspace, /lord, /home/docker or /app/astropy.
    """
    df = TASKS / task / "Dockerfile"
    if df.exists():
        m = re.findall(r"^WORKDIR\s+(\S+)", df.read_text(errors="ignore"), re.M)
        if m:
            return m[-1].strip().rstrip("/") or "/"
    return "/app"


def seed_exists(task: str) -> set[str]:
    """Paths that actually EXIST before the agent runs.

    Only the Dockerfile counts. The instruction naming a path proves the agent knows
    the name, not that the file is there -- most instructions name the OUTPUT the
    agent has to produce. Seeding those as EXISTS would hide every creation and make
    a write look like an overwrite.
    """
    out: set[str] = set()
    df = TASKS / task / "Dockerfile"
    if df.exists():
        for line in df.read_text(errors="ignore").splitlines():
            if line.startswith(("COPY", "ADD")):
                parts = line.split()
                if len(parts) >= 3 and parts[-1].startswith("/"):
                    out.add(posixpath.normpath(parts[-1]))
            m = re.match(r"RUN\s+mkdir\s+(?:-p\s+)?(/\S+)", line)
            if m:
                out.add(posixpath.normpath(m.group(1)))
    return out


def seed_ledger(task: str) -> set[str]:
    """Paths the agent legitimately knows the name of before it does anything."""
    out: set[str] = set()
    y = TASKS / task / "task.yaml"
    if y.exists():
        txt = y.read_text(errors="ignore")
        m = re.search(r"instruction:\s*\|-?\n(.*?)\n[a-z_]+:", txt, re.S)
        if m:
            out |= set(re.findall(r"/(?:app|root|home|etc|var|usr|opt|tmp|srv|data)[/\w.\-]*[\w]",
                                  m.group(1)))
    df = TASKS / task / "Dockerfile"
    if df.exists():
        for line in df.read_text(errors="ignore").splitlines():
            if line.startswith(("COPY", "ADD")):
                parts = line.split()
                if len(parts) >= 3 and parts[-1].startswith("/"):
                    out.add(posixpath.normpath(parts[-1]))
    return out


def convert_cast(path: Path, task: str) -> list[dict]:
    cwd = workdir_for(task)
    stack: list[str] = []
    calls: list[dict] = []
    for step in F.read_mini_cast(path):
        segs = F.clean(step)
        for seg in segs:
            for _ in range(seg.subshell_open):
                stack.append(cwd)
            acts, new_cwd = F.to_actions(seg, cwd)
            base = {
                "step": step.index,
                "raw": seg.text,
                "cwd": cwd,
                "exit_code": step.returncode,
                # A step split by && or || carries one exit code for the whole step,
                # so fs.stat may only use it when the step is a single segment.
                "exit_code_attributable": len(segs) == 1,
            }
            calls.extend(_calls_for(acts, seg, base))
            cwd = new_cwd
            for _ in range(seg.subshell_close):
                if stack:
                    cwd = stack.pop()
    return calls


def _calls_for(acts, seg, base) -> list[dict]:
    if not acts:
        argv = F._argv(seg.text)
        head = posixpath.basename(argv[0]) if argv else ""
        while head in F.PREFIXES and len(argv) > 1:
            argv = argv[1:]
            head = posixpath.basename(argv[0])
        if head in F.STATELESS:
            return [{**base, "op": "sys.noop", "args": {"command": seg.text}, "rule": head}]
        rule = F._BY_CMD.get(head)
        if rule is not None or head in ("tar", ".", "source"):
            # Known operation, but no path operand -- `python3 -c "..."`, `head -5`
            # reading stdin. Must NOT be folded into sys.opaque: the three ways of
            # not knowing (no operation / no path / no effect) degrade the machine
            # differently and have to stay countable apart.
            op = OP.get(rule.op, "fs.exec") if rule is not None else "archive.unpack"
            return [{**base, "op": op, "args": {"path": None}, "no_path_operand": True,
                     "rule": f"{head} without a path operand"}]
        return [{**base, "op": "sys.opaque", "args": {"command": seg.text},
                 "rule": head or "?"}]

    # cp/mv arrive decomposed; recombine so the emitted call matches the spec.
    rules = [a.rule for a in acts]
    if any(r.startswith("cp ") for r in rules) or any(r.startswith("mv ") for r in rules):
        src = next((a for a in acts if a.rule.endswith("source")), None)
        dst = next((a for a in acts if a.rule.endswith("destination")), None)
        if src and dst:
            moved = any(a.op == F.DELETE for a in acts)
            return [{**base, "op": "fs.move" if moved else "fs.copy",
                     "args": {"src": src.path, "dst": dst.path,
                              "unresolved": src.path is None or dst.path is None},
                     "rule": src.rule.rsplit(" ", 1)[0]}]

    if any("tar" in a.rule for a in acts):
        arch = next((a for a in acts if "archive" in a.rule), None)
        members = [a.path for a in acts if "member" in a.rule]
        if arch is not None:
            pack = arch.op == F.CREATE
            args = {"archive": arch.path}
            if pack:
                args["members"] = members
            return [{**base, "op": "archive.pack" if pack else "archive.unpack",
                     "args": args, "rule": arch.rule}]

    out = []
    for a in acts:
        if a.op == F.UNRESOLVED:
            # Keep the operation the rule intended. Collapsing every unresolvable
            # argument to fs.read would make `rule` contradict `op` in the output.
            intended = a.rule.rsplit("-> ", 1)[-1].strip() if "->" in a.rule else ""
            out.append({**base, "op": OP.get(intended, "sys.opaque"),
                        "args": {"path": None, "unresolved": True}, "rule": a.rule})
            continue
        op = OP.get(a.op)
        if op is None:
            continue
        args: dict = {"path": a.path}
        if op == "fs.delete":
            args["recursive"] = bool(re.search(r"\s-\w*[rR]", seg.text))
        if op == "fs.chdir":
            args["durable"] = not seg.piped
        out.append({**base, "op": op, "args": args, "rule": a.rule})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--task", help="convert only traces of this task, and print them")
    a = ap.parse_args()

    counts: collections.Counter = collections.Counter()
    records = []
    for cast in sorted(a.root.rglob("agent.cast")):
        task = cast.parts[-4].split(".")[0]
        if a.task and task != a.task:
            continue
        calls = convert_cast(cast, task)
        trace_id = "/".join(cast.parts[-4:-2])
        for c in calls:
            counts[c["op"]] += 1
            records.append({"trace": trace_id, "task": task, **c})

    if a.task or not a.out:
        for r in records:
            args = {k: v for k, v in r["args"].items() if v not in (None, False, [])}
            print(f"s{r['step']:<3} {r['op']:<14} {json.dumps(args, ensure_ascii=False):<58} "
                  f"cwd={r['cwd']:<12} <- {r['raw'][:60]}")
    if a.out:
        with a.out.open("w") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\nwrote {len(records)} calls to {a.out}")
    print("\ncalls by operation")
    for k, n in counts.most_common():
        print(f"   {n:6d}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
