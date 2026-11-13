import argparse
import json
from pathlib import Path
from . import QuerySession, TrajectorySession


def main():
    parser = argparse.ArgumentParser(
        description="Read-only snapshot queries and recorded-trajectory QA."
    )
    parser.add_argument(
        "snapshot",
        type=Path,
        help="Snapshot JSON or a versioned PolicyScope trajectory",
    )
    parser.add_argument("query", nargs="?", help="Read-only ?- query")
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
    if args.snapshot.stat().st_size > 64 * 1024 * 1024:
        parser.error("Evidence file exceeds 64 MiB; select a shorter episode.")
    value = json.loads(args.snapshot.read_text())
    if value.get("format") == "policyscope-trajectory":
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
            from policyscope.adapters.compatible import Connection

            result = session.ask(
                args.question, Connection(json.loads(args.connection.read_text()))
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
