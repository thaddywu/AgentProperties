"""Run one frozen Base App replenishment cycle with SafeMA v2 installed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

INTEGRATION_ROOT = Path(__file__).resolve().parent
APP_ROOT = INTEGRATION_ROOT.parent / "base-app"
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SHARED_ROOT = REPOSITORY_ROOT / "safema-v2"

for path in (SHARED_ROOT, APP_ROOT / "src", INTEGRATION_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from replenishment.app import Application  # noqa: E402
from replenishment.domain import TriggerKind  # noqa: E402
from replenishment.reporting import run_detail_report  # noqa: E402
from replenishment_safema.integration import install_for_application  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--metadata-db", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    with Application.open(args.config) as app:
        runtime = install_for_application(
            app,
            owner_config_path=args.config,
            metadata_db=args.metadata_db,
        )
        try:
            outcome = app.engine.execute(TriggerKind.MANUAL)
            payload = {
                "base_app": run_detail_report(app, outcome.run.run_id),
                "safema": {"decisions": runtime.registry.decisions()},
            }
        finally:
            runtime.close()

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(
            f"{payload['base_app']['run']['run_id']}: "
            f"{payload['base_app']['run']['status']}"
        )
        for decision in payload["safema"]["decisions"]:
            print(
                f"SafeMA {decision['decision_id']}: {decision['decision']} "
                f"raw_invoked={decision['raw_invoked']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
