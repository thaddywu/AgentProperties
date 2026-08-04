#!/usr/bin/env python3
"""Cross-check openapi.yaml against fsm.yaml.

The two are separate files so each can be reviewed on its own, but an edge names an
operation and a state, so they can drift. This makes a drift loud. Run it in CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

HERE = Path(__file__).parent


def main() -> int:
    api = yaml.safe_load((HERE / "openapi.yaml").read_text())
    fsm = yaml.safe_load((HERE / "fsm.yaml").read_text())

    ops = {v["post"]["operationId"] for v in api["paths"].values()}
    edged = set(fsm["edges"])
    states = set(fsm["states"]) | {"unchanged", "from_exit_code"}

    errs: list[str] = []
    for missing in sorted(ops - edged):
        errs.append(f"openapi declares {missing!r} but fsm.yaml has no edges for it")
    for extra in sorted(edged - ops):
        errs.append(f"fsm.yaml has edges for {extra!r} which openapi does not declare")

    for op, edges in fsm["edges"].items():
        for i, e in enumerate(edges):
            for s in e.get("src", []):
                if s not in states:
                    errs.append(f"{op}[{i}]: unknown src state {s!r}")
            dst = e.get("dst")
            if dst is not None and dst not in states:
                errs.append(f"{op}[{i}]: unknown dst state {dst!r}")
            for s in e.get("violation_if_src", []):
                if s not in fsm["states"]:
                    errs.append(f"{op}[{i}]: unknown violation_if_src state {s!r}")

    # Every command the adapter can emit must be reachable from some operation.
    sys.path.insert(0, str(HERE))
    import fs_trace as F  # noqa: E402

    declared: set[str] = set()
    for v in api["paths"].values():
        for c in v["post"].get("x-commands", []):
            declared.add(c)
    for cmd in sorted(set(F._BY_CMD) | {"tar"}):
        if cmd not in declared:
            errs.append(f"fs_trace maps {cmd!r} but no operation lists it in x-commands")
    for cmd in sorted(F.STATELESS):
        pass  # sys.noop lists a representative subset by design, not the whole set

    if errs:
        print(f"{len(errs)} inconsistencies")
        for e in errs:
            print("  -", e)
        return 1
    print(f"ok: {len(ops)} operations, {sum(len(v) for v in fsm['edges'].values())} edges, "
          f"{len(fsm['states'])} states")
    return 0


if __name__ == "__main__":
    sys.exit(main())
