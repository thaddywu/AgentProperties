import argparse
import json
from pathlib import Path

from .adapters.compatible import Connection
from .pipeline import TranslationFailure, translate


def main():
    parser = argparse.ArgumentParser(
        description="Translate a UTF-8 policy into an isolated review draft."
    )
    parser.add_argument("policy", type=Path)
    parser.add_argument("--binding", required=True, type=Path)
    parser.add_argument("--connection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)

    def save(name, value):
        path = args.output / name
        with path.open("x", encoding="utf-8") as stream:
            path.chmod(0o600)
            json.dump(value, stream, ensure_ascii=False, indent=2)

    records = []

    def record(entry):
        records.append(entry)
        save(f"attempt-{len(records)}.json", entry)

    connection = Connection(json.loads(args.connection.read_text()))
    try:
        review = translate(
            args.policy.read_text(encoding="utf-8"),
            json.loads(args.binding.read_text()),
            connection,
            name=args.policy.name,
            record=record,
            model_metadata=connection.metadata,
        )
        save("review.json", review)
        save("usage.json", connection.usage)
    except TranslationFailure as error:
        save("failure.json", {"error": str(error), "usage": connection.usage})
        parser.exit(1, "Translation failed; see the private output directory.\n")
    print("Review draft saved; no runtime policy installed.")


if __name__ == "__main__":
    main()
