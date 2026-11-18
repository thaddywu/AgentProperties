"""One original-app smoke scenario using LabCluster's explicit offline backend.

Set APP_DIR to the original LabCluster checkout. This tests actual app effects;
the deterministic backend is an offline fixture, not a live model experiment.
"""

import argparse
import json
import os
from pathlib import Path
import sys

APP_DIR = Path(os.environ.get("ORIGINAL_APP_DIR", "original-app"))
CASES = ["T1_priority_queue"]


def start_app():
    sys.path.insert(0, str(APP_DIR.resolve()))
    from agents.deterministic import DeterministicBackend
    from phase1.run import run_scenario
    return run_scenario, DeterministicBackend()


def check_result(result):
    jobs = result["final_state"]["jobs"]
    return (
        result["result"]["error"] is None
        and len(jobs) == 2
        and {job["owner"] for job in jobs} == {"Master", "PhD"}
        and all(job["state"] == "COMPLETED" for job in jobs)
        and all(node["run_id"] is None for node in result["final_state"]["nodes"])
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--side", choices=["original"], required=True)
    parser.add_argument("--output_dir", default="runs", type=Path)
    parser.add_argument("--sample", default=1, type=int)
    args = parser.parse_args()
    if args.sample < 1:
        parser.error("--sample must be positive")
    for case in [args.case] if args.case else CASES:
        for sample in range(1, args.sample + 1):
            directory = args.output_dir / case / args.side / f"sample-{sample}"
            directory.mkdir(parents=True, exist_ok=False)
            complete = False
            try:
                run_scenario, backend = start_app()
                result = run_scenario(case, backend)
                complete = check_result(result)
                artifacts = directory / "artifacts"
                artifacts.mkdir()
                (artifacts / "application.json").write_text(json.dumps(result, indent=2))
            finally:
                (directory / "result.json").write_text(json.dumps({"task_complete": complete}))


if __name__ == "__main__":
    main()
