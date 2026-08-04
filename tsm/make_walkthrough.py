#!/usr/bin/env python3
"""Render one converted trace as a replay table: tsm/walkthrough.md.

Rows are grouped by SEGMENT, not by agent step. One step often holds several commands
joined by `&&`, and grouping by step made four independent `ls` calls look like the
output of a single one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import convert as C  # noqa: E402
import fs_trace as F  # noqa: E402
from fs_typestate import Ledger, Machine  # noqa: E402

TASK = "decommissioning-service-with-sensitive-data"


def main() -> int:
    calls = [json.loads(l) for l in (HERE / "calls.jsonl").open()]
    calls = [c for c in calls if c["task"] == TASK]
    trace = calls[0]["trace"]
    calls = [c for c in calls if c["trace"] == trace]

    m = Machine.load(HERE / "fsm.yaml")
    seed, exists, cwd = C.seed_ledger(TASK), C.seed_exists(TASK), C.workdir_for(TASK)
    state = {p: "EXISTS" for p in exists}
    ledger = Ledger()
    for p in seed | exists:
        ledger.add(p)
    ledger.add_subtree(cwd)

    rows: list[tuple] = []
    for call in calls:
        op, args = call["op"], call.get("args") or {}
        raw, step = call["raw"], call["step"]
        if op == "sys.noop":
            continue
        if op == "sys.opaque":
            rows.append((step, raw, op, "-", "-", "blind: no typed operation"))
            continue
        if args.get("unresolved") or call.get("no_path_operand"):
            rows.append((step, raw, op, "-", "-", "blind: no resolvable path"))
            continue
        for edge in m.edges.get(op) or []:
            role = edge.get("resource")
            if not role or role == "none":
                continue
            paths = list(args.get("members") or []) if role == "member" else [args.get(role)]
            for path in paths:
                if not path:
                    continue
                scoped = F.in_scope(path)
                st = state.get(path, m.initial)
                note = ""
                if scoped:
                    if "in ledger" in (edge.get("guard") or "") and path not in ledger:
                        note = "VIOLATION  UNBOUND_IDENTIFIER"
                    elif st in (edge.get("violation_if_src") or []):
                        note = "VIOLATION  UNDEFINED_TRANSITION"
                new, dst = st, edge.get("dst")
                rc, attr = call.get("exit_code"), call.get("exit_code_attributable")
                attr = bool(attr) and rc is not None
                if dst == "from_exit_code":
                    if attr and rc not in (126, 127):
                        new = "EXISTS" if rc == 0 else "ABSENT"
                    ledger.add(path)
                    if op == "fs.list":
                        ledger.add_subtree(path)
                elif dst not in (None, "unchanged") and not (attr and rc != 0):
                    new = dst
                    if dst == "EXISTS":
                        ledger.add(path)
                if scoped:
                    state[path] = new
                elif not note:
                    note = "out of scope"
                rows.append((step, raw, op, path,
                             f"{st} -> {new}" if new != st else st, note))

    out = [
        "# Replay of one trace",
        "",
        f"Task `{TASK}`, trial `{trace.split('/')[-1]}`.",
        "terminal-bench-core 0.1.1, mini-swe-agent + claude-4-sonnet, from the official",
        "leaderboard repository.",
        "",
        "Rows are grouped by COMMAND. One agent step often holds several commands joined",
        "by `&&`, and each becomes its own call — step 0 below is five commands, not one.",
        "",
        "Seed state, derived statically before the agent runs:",
        "",
        "```",
        f"cwd     {cwd}",
    ]
    for p in sorted(exists):
        out.append(f"EXISTS  {p:<44} Dockerfile puts it there")
    for p in sorted(seed - exists):
        out.append(f"known   {p:<44} named by the instruction: the agent knows the name,")
        out.append(f"        {'':<44} which is not the same as the file being there")
    out += ["```", "",
            "Everything else starts `UNKNOWN` — a container ships a whole filesystem, so a",
            "path the agent has not touched is unobserved, not absent.", "", "```",
            f"{'step':<5} {'operation':<15} {'path':<46} {'state':<20} note"]

    last = None
    for step, raw, op, path, st, note in rows:
        if (step, raw) != last:
            out.append(f"--- step {step}:  {raw.splitlines()[0][:100]}")
            last = (step, raw)
        out.append(f"{'':<5} {op:<15} {str(path):<46} {st:<20} {note}".rstrip())
    out += ["```", ""]

    viol = sum(1 for r in rows if r[5].startswith("VIOLATION"))
    out.append(f"**{viol} violations.** This trial passed its tests, so that is the expected")
    out.append("result: the machine earns its keep by not firing on a correct trace.")

    (HERE / "walkthrough.md").write_text("\n".join(out) + "\n")
    print(f"{len(rows)} rows, {viol} violations -> tsm/walkthrough.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
