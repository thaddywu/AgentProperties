import argparse
import json
from pathlib import Path
from . import QuerySession


def main():
    parser = argparse.ArgumentParser(
        description="Read-only query of a captured policy snapshot."
    )
    parser.add_argument(
        "snapshot",
        type=Path,
        help="JSON containing binding, source, inputs and optional versions",
    )
    parser.add_argument("query", help="Read-only ?- query")
    args = parser.parse_args()
    session = QuerySession(**json.loads(args.snapshot.read_text()))
    print(json.dumps(session.query(args.query), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
