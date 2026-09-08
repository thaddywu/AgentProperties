"""Command-line interface: manual runs, the scheduler, and inspection."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Sequence

from . import reporting
from .app import Application
from .config import load_config
from .domain import AttemptState, RunStatus, TriggerKind
from .errors import ConfigError, ReplenishmentError, RunLockError
from .journal import DuplicateScheduledRun
from .scheduler import Scheduler

EXIT_OK = 0
EXIT_RUN_FAILED = 1
EXIT_ERROR = 2


def _emit(payload: dict[str, Any], text: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=False, default=str))
    else:
        print(text)


def _world_dirs(config) -> list[Path]:
    roots: list[Path] = []
    for slot in ("inventory_ledger", "sales_history", "calendar"):
        raw = config.adapters[slot].options.get("world_dir")
        if isinstance(raw, str):
            roots.append(config.resolve_path(raw))
    for spec in config.suppliers.values():
        raw = spec.options.get("world_dir")
        if isinstance(raw, str):
            roots.append(config.resolve_path(raw))
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


# -- commands --------------------------------------------------------------


def cmd_init_db(args: argparse.Namespace) -> int:
    with Application.open(args.config, create_schema=True, recover=False) as app:
        print(f"application database ready at {app.config.database_path}")
    return EXIT_OK


def cmd_init_world(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    source = (
        Path(args.source).expanduser().resolve()
        if args.source
        else config.base_dir / "world"
    )
    if not source.is_dir():
        raise ConfigError(f"fixture world directory not found: {source}")
    targets = _world_dirs(config)
    if not targets:
        raise ConfigError("the configuration declares no local world directory")
    for target in targets:
        if target == source:
            raise ConfigError(
                f"refusing to copy {source} onto itself; point 'world_dir' at a "
                "working copy such as state/world"
            )
        if target.exists() and any(target.iterdir()) and not args.force:
            raise ConfigError(
                f"{target} already contains mock world state; pass --force to replace it"
            )
        if target.exists() and args.force:
            shutil.rmtree(target)
        shutil.copytree(source, target)
        print(f"mock world initialized at {target} from {source}")
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    with Application.open(args.config) as app:
        outcome = app.engine.execute(TriggerKind.MANUAL)
        report = reporting.run_detail_report(app, outcome.run.run_id)
        _emit(report, reporting.render_run_outcome(report), args.json)
        return (
            EXIT_RUN_FAILED
            if outcome.run.status is RunStatus.FAILED
            else EXIT_OK
        )


def cmd_scheduler(args: argparse.Namespace) -> int:
    with Application.open(args.config) as app:
        scheduler = Scheduler(app)
        status = scheduler.status()
        print(
            f"scheduler started; local time {status.local_now.isoformat()}, "
            f"daily run at {status.daily_run_time}, next due "
            f"{status.next_due_at.isoformat()}"
        )
        outcomes = scheduler.serve(max_cycles=args.max_cycles)
        for outcome in outcomes:
            print(
                f"scheduled run {outcome.run.run_id} for "
                f"{outcome.run.business_date.isoformat()}: {outcome.run.status.value}"
            )
        if not outcomes:
            print("no scheduled run was due")
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    with Application.open(args.config, recover=False) as app:
        report = reporting.status_report(app)
        _emit(report, reporting.render_status(report), args.json)
    return EXIT_OK


def cmd_runs(args: argparse.Namespace) -> int:
    with Application.open(args.config, recover=False) as app:
        report = reporting.runs_report(app, args.limit)
        _emit(report, reporting.render_runs(report), args.json)
    return EXIT_OK


def cmd_show_run(args: argparse.Namespace) -> int:
    with Application.open(args.config, recover=False) as app:
        try:
            report = reporting.run_detail_report(app, args.run_id)
        except KeyError:
            print(f"no such run: {args.run_id}", file=sys.stderr)
            return EXIT_ERROR
        _emit(report, reporting.render_run_detail(report), args.json)
    return EXIT_OK


def cmd_decisions(args: argparse.Namespace) -> int:
    with Application.open(args.config, recover=False) as app:
        run_id = args.run
        if run_id is None:
            last = app.journal.last_completed_run() or (
                app.journal.list_runs(1)[0] if app.journal.list_runs(1) else None
            )
            if last is None:
                print("no runs recorded", file=sys.stderr)
                return EXIT_ERROR
            run_id = last.run_id
        report = reporting.decisions_report(app, run_id, args.sku)
        _emit(report, reporting.render_decisions(report), args.json)
    return EXIT_OK


def cmd_attempts(args: argparse.Namespace) -> int:
    with Application.open(args.config, recover=False) as app:
        states = (
            [AttemptState(value) for value in args.state] if args.state else None
        )
        report = reporting.attempts_report(app, states=states, run_id=args.run)
        _emit(report, reporting.render_attempts(report), args.json)
    return EXIT_OK


def cmd_orders(args: argparse.Namespace) -> int:
    with Application.open(args.config, recover=False) as app:
        report = reporting.orders_report(app, args.sku)
        _emit(report, reporting.render_orders(report), args.json)
    return EXIT_OK


def cmd_supplier_calls(args: argparse.Namespace) -> int:
    with Application.open(args.config, recover=False) as app:
        report = reporting.supplier_calls_report(app, args.supplier, args.limit)
        _emit(report, reporting.render_supplier_calls(report), args.json)
    return EXIT_OK


# -- parser ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="replenish",
        description=(
            "Multi-Supplier Replenishment Automation for one convenience store."
        ),
    )
    parser.add_argument(
        "--config",
        required=True,
        help="path to the owner configuration file (JSON or TOML)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add(name: str, handler, help_text: str) -> argparse.ArgumentParser:
        sub = subparsers.add_parser(name, help=help_text)
        sub.set_defaults(handler=handler)
        return sub

    add("init-db", cmd_init_db, "create the application SQLite schema")

    world = add(
        "init-world", cmd_init_world, "copy example mock-world state into place"
    )
    world.add_argument(
        "--source",
        help="fixture world directory to copy (default: <config dir>/world)",
    )
    world.add_argument(
        "--force",
        action="store_true",
        help="replace existing mock world state in the configured world directory",
    )

    run = add("run", cmd_run, "execute one manual replenishment run now")
    run.add_argument("--json", action="store_true", help="emit JSON")

    scheduler = add(
        "scheduler", cmd_scheduler, "start the long-running daily scheduler"
    )
    scheduler.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="stop after this many polling cycles (used for demos and tests)",
    )

    status = add("status", cmd_status, "show scheduler status and the last run")
    status.add_argument("--json", action="store_true", help="emit JSON")

    runs = add("runs", cmd_runs, "list runs, newest first")
    runs.add_argument("--limit", type=int, default=20)
    runs.add_argument("--json", action="store_true", help="emit JSON")

    show = add("show-run", cmd_show_run, "show one run with its decisions")
    show.add_argument("run_id")
    show.add_argument("--json", action="store_true", help="emit JSON")

    decisions = add("decisions", cmd_decisions, "show per-SKU decisions and inputs")
    decisions.add_argument("--run", help="run ID (default: the newest run)")
    decisions.add_argument("--sku")
    decisions.add_argument("--json", action="store_true", help="emit JSON")

    attempts = add(
        "attempts", cmd_attempts, "show purchase attempts and reconciliation history"
    )
    attempts.add_argument(
        "--state",
        action="append",
        choices=[item.value for item in AttemptState],
        help="filter by attempt state; may be repeated",
    )
    attempts.add_argument("--run")
    attempts.add_argument("--json", action="store_true", help="emit JSON")

    orders = add("orders", cmd_orders, "show recorded supplier orders and statuses")
    orders.add_argument("--sku")
    orders.add_argument("--json", action="store_true", help="emit JSON")

    calls = add(
        "supplier-calls",
        cmd_supplier_calls,
        "show the local mock world's raw supplier call log",
    )
    calls.add_argument("--supplier")
    calls.add_argument("--limit", type=int, default=None)
    calls.add_argument("--json", action="store_true", help="emit JSON")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except DuplicateScheduledRun as exc:
        print(f"scheduled run not started: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except RunLockError as exc:
        print(f"run rejected: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except ReplenishmentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover - exercised through __main__.py
    raise SystemExit(main())
