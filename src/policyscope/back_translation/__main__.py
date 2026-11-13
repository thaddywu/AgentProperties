"""Read an implementation evidence bundle without supplying source intent."""

import argparse
import json
from pathlib import Path

from policyscope.adapters.compatible import Connection
from policyscope.core.artifacts import save
from .execution import describe_execution


def main():
    parser = argparse.ArgumentParser(
        description="Independently describe implemented policy checks."
    )
    parser.add_argument(
        "implementation", type=Path, help="JSON containing rules, binding and evidence"
    )
    parser.add_argument("--connection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    value = json.loads(args.implementation.read_text())
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    model = Connection(json.loads(args.connection.read_text()))
    attempts = []

    def record(entry):
        attempts.append(entry)
        save(args.output / "attempts.json", attempts)

    # Only these fields cross the reverse-model boundary. Original policy and
    # forward-plan fields, if present in the input, are never forwarded.
    procedures = describe_execution(
        value["rules"], value["binding"], value["evidence"], model, record
    )
    save(args.output / "execution.json", dict(version=1, procedures=procedures))
    save(args.output / "usage.json", model.usage)


if __name__ == "__main__":
    main()
