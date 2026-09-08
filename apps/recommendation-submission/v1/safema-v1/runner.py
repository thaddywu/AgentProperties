"""Run the frozen RecSub CLI with SafeMA installed around it."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


INTEGRATION_ROOT = Path(__file__).resolve().parent
APP_VERSION_ROOT = INTEGRATION_ROOT.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-app", default=str(APP_VERSION_ROOT / "base-app"))
    parser.add_argument("--metadata-db", required=True)
    parser.add_argument("--effects", default=str(INTEGRATION_ROOT / "models/api-effects-v1.yaml"))
    parser.add_argument("--origins", default=str(INTEGRATION_ROOT / "models/trusted-origins-v1.yaml"))
    parser.add_argument(
        "--policy",
        default=str(INTEGRATION_ROOT / "policies/recommendation-disclosure-v1.yaml"),
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
