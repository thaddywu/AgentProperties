#!/usr/bin/env python3
"""Run a test file without the workbench or a student frontend."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for directory in ("runtime/python", "translation/python", "query/python", "evaluation"):
    sys.path.insert(0, str(ROOT / directory))
from policy_evaluation.example import Application
from policy_evaluation.porting.application import PortedApplication
from policy_evaluation.study import Study
from policy_evaluation.cases import run_cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument(
        "--data",
        required=True,
        type=Path,
        help="Private result directory; do not use a running server's directory",
    )
    parser.add_argument("--ported-app", type=Path)
    args = parser.parse_args()
    app = PortedApplication(args.ported_app) if args.ported_app else Application()
    study = Study(args.data, app)
    if args.cases.stat().st_size > 200_000:
        parser.error("Test file exceeds 200 KB")
    pairs = run_cases(study, json.loads(args.cases.read_text()))
    print(
        json.dumps(
            dict(
                comparisons=len(pairs),
                comparable=sum(p["comparable"] for p in pairs),
                summary=study.summary(),
            ),
            indent=2,
        )
    )
    return 0 if all(p["comparable"] for p in pairs) else 1


if __name__ == "__main__":
    sys.exit(main())
