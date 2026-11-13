"""Operator entry point: select source and a private model connection once."""

import argparse
import json
from pathlib import Path

from policyscope.adapters.compatible import Connection

from .agent import INSTRUCTIONS, Porter


def main():
    parser = argparse.ArgumentParser(
        description="Inspect, generate, test and repair an isolated LabCluster port."
    )
    parser.add_argument("--source", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--connection",
        required=True,
        type=Path,
        help="Private standard connection JSON; never copied into the application or sandbox",
    )
    parser.add_argument("--image", default="policy-portin:local")
    parser.add_argument("--max-turns", type=int, default=35)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue the existing audit log; checks must pass again",
    )
    parser.add_argument(
        "--repair-validation",
        action="store_true",
        help="Expose failed validation as regression tests; preserve the first independent result",
    )
    args = parser.parse_args()
    if args.repair_validation and not args.resume:
        parser.error("--repair-validation requires --resume")
    settings = json.loads(args.connection.read_text())
    generate = Connection(settings, instructions=INSTRUCTIONS)
    if args.resume:
        porter = Porter.resume(
            args.output,
            generate,
            backtranslate=Connection(settings),
            max_turns=args.max_turns,
            repair_validation=args.repair_validation,
        )
    else:
        if not args.source or not args.policy:
            parser.error("--source and --policy are required for a new port")
        porter = Porter(
            args.source,
            args.policy,
            args.output,
            generate,
            backtranslate=Connection(settings),
            image=args.image,
            max_turns=args.max_turns,
        )
    result = porter.run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] not in ("validated", "validated-after-repair"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
