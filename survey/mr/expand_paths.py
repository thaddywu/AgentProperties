#!/usr/bin/env python3
"""
Mechanically flatten a ToolBench DFSDT search tree into self-contained linear traces.

`answer_generation.tree` is a search tree, so no single record in an answer file is a
readable "one run of the agent". This script expands it: every root-to-leaf path becomes
one standalone trace carrying its own query, its own ordered steps with arguments and
observations, and its own leaf status. The expansion is purely structural -- it walks
node types and children, and never interprets content.

Per step it also records `visible_siblings`: the alternatives DFSDT had already tried at
that same state, which its backtrack prompt injects into the agent's context together
with their `function_output`. Those are part of what the agent saw and are kept so a
reader can tell a genuinely blind call from an informed one.

Optionally each step is annotated with the typestate findings from `typestate.py`, so a
violation is shown in place rather than in a separate table.

    python expand_paths.py --trace ../datasets/ToolBench/data/answer/G3_answer/1256_ChatGPT_DFS_woFilter_w2.json
    python expand_paths.py --tool sms77io --only-violations --md pilot.md
    python expand_paths.py --tool sms77io --limit 20 --jsonl paths.jsonl
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typestate as T


# ===========================================================================
# Expansion
# ===========================================================================


@dataclass
class Step:
    index: int  # 1-based position within this path
    expand_num: int | None  # ToolBench's global expansion counter
    depth: int | None
    op_raw: str  # function name as the agent emitted it
    op: str | None  # resolved endpoint name, None if not in the tool spec
    args: dict[str, Any]
    error: str
    response: Any
    truncated: bool
    raw_body: str
    outcome: str  # ok | failed | unknown
    thought: str  # the Thought node immediately preceding this Action, if any
    visible_siblings: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FlatPath:
    trace: str  # "<group>/<file>"
    query_id: str
    path_id: int
    n_paths: int
    query: str
    exposed_functions: list[str]
    finish_type: str | None
    win: bool | None
    leaf: dict[str, Any]  # is_terminal / pruned / finished / node_type of the leaf
    steps: list[Step]

    @property
    def n_violations(self) -> int:
        return sum(len(s.findings) for s in self.steps)

    def as_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["steps"] = [dict(s.__dict__) for s in self.steps]
        d["n_violations"] = self.n_violations
        return d


def _outcome(obs: T.Observation) -> str:
    return {True: "ok", False: "failed", None: "unknown"}[obs.ok]


def _sibling_record(action_node: dict) -> dict[str, Any]:
    inp = (action_node.get("children") or [{}])[0]
    obs = T.parse_observation(inp.get("observation"))
    return {
        "op_raw": action_node.get("description") or "",
        "args": T._loose(inp.get("description")),
        "outcome": _outcome(obs),
        "response_excerpt": str(obs.response)[:160],
    }


def expand(answer: dict, trace_id: str, resolve=lambda s: None) -> list[FlatPath]:
    """Every root-to-leaf path of the tree, as an independent linear trace."""
    tree = (answer.get("tree") or {}).get("tree")
    ag = answer.get("answer_generation") or {}
    if not tree:
        return []

    raw_paths: list[tuple[list[Step], dict]] = []

    def rec(node: dict, acc: list[Step], siblings: list[dict], pending_thought: str) -> None:
        acc2, thought = acc, pending_thought
        if node.get("node_type") == "Action":
            inp = (node.get("children") or [{}])[0]
            obs = T.parse_observation(inp.get("observation"))
            acc2 = acc + [
                Step(
                    index=len(acc) + 1,
                    expand_num=inp.get("expand_num"),
                    depth=node.get("depth"),
                    op_raw=node.get("description") or "",
                    op=resolve(node.get("description") or ""),
                    args=T._loose(inp.get("description")),
                    error=obs.error,
                    response=obs.response,
                    truncated=obs.truncated,
                    raw_body=obs.raw_body,
                    outcome=_outcome(obs),
                    thought=thought,
                    visible_siblings=list(siblings),
                )
            ]
            thought = ""
        elif node.get("node_type") == "Thought":
            thought = node.get("description") or ""

        kids = node.get("children") or []
        if not kids:
            if acc2:
                raw_paths.append((acc2, node))
            return
        seen: list[dict] = []
        for c in kids:
            rec(c, acc2, seen, thought)
            if c.get("node_type") == "Action":
                seen = seen + [_sibling_record(c)]

    rec(tree, [], [], "")

    # Deduplicate paths with an identical (op, args) sequence: DFSDT re-expands a state
    # several times and those replays are the same run as far as a reader is concerned.
    # Steps are copied per path: prefixes are shared between paths, and annotation
    # mutates a step, so sharing would smear one path's findings across its siblings.
    out: list[FlatPath] = []
    sigs: set[tuple] = set()
    for steps, leaf in raw_paths:
        sig = tuple((s.op_raw, json.dumps(s.args, sort_keys=True)) for s in steps)
        if sig in sigs:
            continue
        sigs.add(sig)
        out.append(
            FlatPath(
                trace=trace_id,
                query_id=trace_id.split("/")[-1].split("_")[0],
                path_id=len(out),
                n_paths=0,
                query=ag.get("query", ""),
                exposed_functions=[f["name"] for f in ag.get("function", [])],
                finish_type=ag.get("finish_type"),
                win=answer.get("win"),
                leaf={
                    "node_type": leaf.get("node_type"),
                    "is_terminal": leaf.get("is_terminal"),
                    "pruned": leaf.get("pruned"),
                    "finished": leaf.get("finished"),
                    "depth": leaf.get("depth"),
                },
                steps=[dataclasses.replace(st, findings=[]) for st in steps],
            )
        )
    for p in out:
        p.n_paths = len(out)
    return out


def annotate(paths: list[FlatPath], checker: T.Checker) -> None:
    """Attach typestate findings to the step they occurred on."""
    for p in paths:
        calls = [
            T.Call(
                op_raw=s.op_raw,
                args=s.args,
                obs=T.Observation(s.error, s.response, s.truncated, s.raw_body),
                index=s.index - 1,
                expand_num=s.expand_num,
                visible_siblings=tuple(
                    T.Observation("", sib.get("response_excerpt", ""), False, "")
                    for sib in s.visible_siblings
                ),
            )
            for s in p.steps
        ]
        for f in checker.run(calls, p.trace, p.path_id):
            if 0 <= f.call_index < len(p.steps):
                p.steps[f.call_index].findings.append(
                    {
                        "kind": str(f.kind),
                        "resource": f.resource,
                        "instance": f.instance,
                        "observed_state": f.observed_state,
                        "expected_states": list(f.expected_states or ()),
                        "detail": f.detail,
                    }
                )


# ===========================================================================
# Rendering
# ===========================================================================


def _fmt_args(args: dict[str, Any], width: int = 64) -> str:
    if not args:
        return "()"
    parts = [f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items()]
    s = ", ".join(parts)
    return s if len(s) <= width else s[: width - 1] + "…"


def _fmt_result(step: Step, width: int = 60) -> str:
    if step.error:
        body = step.error
    else:
        body = str(step.response)
    body = " ".join(body.split())
    if len(body) > width:
        body = body[: width - 1] + "…"
    tag = {"ok": "OK  ", "failed": "FAIL", "unknown": "??  "}[step.outcome]
    trunc = " [truncated]" if step.truncated else ""
    return f"{tag} {body}{trunc}"


def render(p: FlatPath, show_thoughts: bool = False) -> str:
    head = f"### {p.trace}  path {p.path_id + 1}/{p.n_paths}"
    if p.n_violations:
        head += f"   [{p.n_violations} violation{'s' if p.n_violations > 1 else ''}]"
    lines = [head, ""]
    lines.append(f"- query: {p.query}")
    lines.append(f"- finish_type: {p.finish_type}   win: {p.win}")
    lines.append(
        "- leaf: "
        + " ".join(f"{k}={v}" for k, v in p.leaf.items() if v is not None)
    )
    lines.append(f"- tools exposed ({len(p.exposed_functions)}): "
                 + ", ".join(p.exposed_functions))
    lines.append("")
    lines.append("```")
    for s in p.steps:
        sib = f" (+{len(s.visible_siblings)} sibling alt shown)" if s.visible_siblings else ""
        name = s.op or f"{s.op_raw}  <not in spec>"
        lines.append(f"{s.index}. [{s.expand_num}] {name}{sib}")
        if show_thoughts and s.thought:
            lines.append(f"      thought: {' '.join(s.thought.split())[:160]}")
        lines.append(f"      args   : {_fmt_args(s.args)}")
        lines.append(f"      result : {_fmt_result(s)}")
        for f in s.findings:
            # A guard fires before the instance key is resolved, so resource/state are
            # empty there; printing "sms(None)=None" would read as a real state.
            if f["instance"] is not None:
                exp = "|".join(f["expected_states"]) or "-"
                loc = f"{f['resource']}({f['instance']})={f['observed_state']}"
                lines.append(f"      !! {f['kind']}  {loc}  requires {exp}")
            elif f["resource"]:
                lines.append(f"      !! {f['kind']}  resource={f['resource']}")
            else:
                lines.append(f"      !! {f['kind']}")
            lines.append(f"         {' '.join(f['detail'].split())[:220]}")
    lines.append("```")
    return "\n".join(lines)


# ===========================================================================
# CLI
# ===========================================================================


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--tool", default="sms77io", choices=sorted(T.FSMS))
    ap.add_argument("--trace", action="append", help="expand specific answer file(s)")
    ap.add_argument("--limit", type=int, default=None, help="max traces to read")
    ap.add_argument("--only-violations", action="store_true", help="keep paths with findings")
    ap.add_argument("--max-paths", type=int, default=None, help="max paths to emit")
    ap.add_argument("--thoughts", action="store_true", help="include the agent's Thought text")
    ap.add_argument("--jsonl", help="write one JSON object per expanded path")
    ap.add_argument(
        "--outdir",
        help="write ONE pretty-printed JSON file per expanded path into this directory, "
        "plus an index.json listing them",
    )
    ap.add_argument("--md", help="write a readable markdown report")
    ap.add_argument("--print", dest="do_print", type=int, default=3, help="paths to print")
    args = ap.parse_args(argv)

    checker = T.Checker(T.FSMS[args.tool], T.op_index(args.tool, T.find_spec(args.tool)), True)
    files = (
        [Path(t) for t in args.trace]
        if args.trace
        else list(T.traces_for_tool(args.tool, args.limit))
    )

    all_paths: list[FlatPath] = []
    n_traces = 0
    for fp in files:
        try:
            answer = json.loads(fp.read_text())
        except Exception:
            continue
        n_traces += 1
        paths = expand(answer, f"{fp.parent.name}/{fp.name}", checker.resolve)
        annotate(paths, checker)
        if args.only_violations:
            paths = [p for p in paths if p.n_violations]
        all_paths.extend(paths)
        if args.max_paths and len(all_paths) >= args.max_paths:
            all_paths = all_paths[: args.max_paths]
            break

    steps = sum(len(p.steps) for p in all_paths)
    viol = sum(p.n_violations for p in all_paths)
    kinds = collections.Counter(f["kind"] for p in all_paths for s in p.steps for f in s.findings)
    print(
        f"{n_traces} traces -> {len(all_paths)} paths, {steps} steps, {viol} findings "
        f"({dict(kinds)})",
        file=sys.stderr,
    )

    if args.outdir:
        out = Path(args.outdir)
        out.mkdir(parents=True, exist_ok=True)
        index = []
        for p in all_paths:
            group = p.trace.split("/")[0].replace("_answer", "")
            name = f"{group}_{p.query_id}_p{p.path_id:03d}.json"
            (out / name).write_text(
                json.dumps(p.as_dict(), ensure_ascii=False, indent=2, default=str) + "\n"
            )
            index.append(
                {
                    "file": name,
                    "trace": p.trace,
                    "query_id": p.query_id,
                    "path_id": p.path_id,
                    "n_paths_in_trace": p.n_paths,
                    "n_steps": len(p.steps),
                    "n_violations": p.n_violations,
                    "kinds": sorted({f["kind"] for st in p.steps for f in st.findings}),
                    "ops": [st.op or st.op_raw for st in p.steps],
                    "finish_type": p.finish_type,
                    "win": p.win,
                    "query": p.query,
                }
            )
        (out / "index.json").write_text(
            json.dumps(
                {
                    "tool": args.tool,
                    "n_traces": n_traces,
                    "n_paths": len(all_paths),
                    "n_steps": steps,
                    "n_findings": viol,
                    "findings_by_kind": dict(kinds),
                    "paths": index,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        print(f"wrote {len(all_paths)} path files + index.json to {out}", file=sys.stderr)

    if args.jsonl:
        with open(args.jsonl, "w") as fh:
            for p in all_paths:
                fh.write(json.dumps(p.as_dict(), ensure_ascii=False, default=str) + "\n")
        print(f"wrote {len(all_paths)} paths to {args.jsonl}", file=sys.stderr)

    body = "\n\n".join(render(p, args.thoughts) for p in all_paths)
    if args.md:
        header = (
            f"# Expanded ToolBench paths -- {args.tool}\n\n"
            f"{n_traces} traces expanded into {len(all_paths)} root-to-leaf paths "
            f"({steps} steps, {viol} typestate findings).\n"
            f"Each section below is one complete, self-contained run: the search tree has "
            f"been flattened so that a path never depends on a sibling subtree.\n\n"
        )
        Path(args.md).write_text(header + body + "\n")
        print(f"wrote {args.md}", file=sys.stderr)

    for p in all_paths[: args.do_print]:
        print(render(p, args.thoughts))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
