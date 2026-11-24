import argparse
import json
from pathlib import Path
from . import QuerySession, TrajectorySession
from policyweave.adapters.model_settings import load_connection
from .timeline import MAX_TRAJECTORY_BYTES


def main():
    parser = argparse.ArgumentParser(
        description="Read-only snapshot queries and recorded-trajectory QA."
    )
    parser.add_argument(
        "snapshot",
        type=Path,
        help="Snapshot JSON or a versioned PolicyWeave trajectory",
    )
    parser.add_argument("query", nargs="?", help="Read-only ?- query")
    parser.add_argument(
        "--rules",
        type=Path,
        help="Historical analysis .dl for execution observations; never replaces a captured online policy",
    )
    parser.add_argument("--event", help="Recorded event ID for a state query")
    parser.add_argument(
        "--verify", action="store_true", help="Replay every recorded gate decision"
    )
    parser.add_argument(
        "--plan",
        type=Path,
        help="JSON admitted trajectory operation; no model required",
    )
    parser.add_argument(
        "--question", help="Natural-language question over recorded evidence"
    )
    parser.add_argument(
        "--connection", type=Path, help="Private compatible model connection for NL QA"
    )
    args = parser.parse_args()
    if args.snapshot.stat().st_size > MAX_TRAJECTORY_BYTES:
        parser.error("Evidence file exceeds 512 MiB; select a shorter episode.")
    value = json.loads(args.snapshot.read_text())
    if args.rules:
        if value.get("format") != "policyscope-timeline":
            parser.error(
                "--rules requires a data-only execution timeline; captured online policies replay unchanged."
            )
        from .execution import execution_analysis

        value = execution_analysis(value, rules=args.rules.read_text())
    if value.get("format") == "policyscope-timeline":
        from .timeline import Timeline
        from .log_query import LogQuerySession

        session = LogQuerySession(Timeline(value))
        if (
            args.verify
            or args.plan
            or args.event
            or bool(args.query) == bool(args.question)
        ):
            parser.error("Choose a read-only query or --question for a timeline.")
        if args.question:
            if not args.connection:
                parser.error(
                    "Natural-language analysis requires an optional model connection."
                )
            from policyweave.adapters.compatible import Connection

            result = session.ask(
                args.question, Connection(load_connection(args.connection))
            )
        else:
            result = session.query(args.query)
    elif value.get("format") == "policyscope-trajectory":
        session = TrajectorySession(value)
        if (
            sum(bool(x) for x in [args.verify, args.plan, args.question, args.query])
            != 1
        ):
            parser.error(
                "Select exactly one of --verify, --plan, --question or a state query."
            )
        if args.verify:
            result = session.verify()
        elif args.plan:
            result = session.run(json.loads(args.plan.read_text()))
        elif args.question:
            if not args.connection:
                parser.error(
                    "NL QA needs an injected model; use --plan for deterministic offline analysis."
                )
            from policyweave.adapters.compatible import Connection

            result = session.ask(
                args.question, Connection(load_connection(args.connection))
            )
        else:
            if not args.event:
                parser.error("A trajectory state query needs --event.")
            result = session.query(args.event, args.query)
    else:
        if args.verify or args.plan or args.question or args.event:
            parser.error(
                "Trajectory operations require recorded gate inputs, not a raw transcript or plain snapshot."
            )
        if not args.query:
            parser.error("A snapshot query is required.")
        result = QuerySession(**value).query(args.query)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.verify and (not result["allMatched"] or result["unresolvedEvents"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
