"""Run the frozen RecSub CLI with SafeMA installed around it."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = ROOT / "safema-v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-app", default=str(ROOT / "v1-impl"))
    parser.add_argument("--metadata-db", required=True)
    parser.add_argument("--effects", default=str(DEFAULTS / "models/api-effects-v1.yaml"))
    parser.add_argument("--origins", default=str(DEFAULTS / "models/trusted-origins-v1.yaml"))
    parser.add_argument(
        "--policy",
        default=str(DEFAULTS / "policies/same-principal-active-destination-v1.yaml"),
    )
    parser.add_argument("recsub_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sys.path.insert(0, str(Path(args.base_app).resolve()))
    from recsub.cli import main as recsub_main

    from .runtime import install

    recsub_args = list(args.recsub_args)
    if recsub_args and recsub_args[0] == "--":
        recsub_args.pop(0)
    runtime = install(
        effect_models_path=args.effects,
        origins_path=args.origins,
        policy_path=args.policy,
        metadata_db=args.metadata_db,
    )
    try:
        return recsub_main(recsub_args)
    finally:
        runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
