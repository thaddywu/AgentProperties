"""Offline compiler CLI. Model translation is an optional, separate authoring step."""

import argparse
import json
from pathlib import Path

from .policy import compile_policy


def main():
    parser = argparse.ArgumentParser(prog="python -m policy_runtime")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Private JSON-lines worker for a trusted parent backend")
    compile_command = commands.add_parser("compile")
    compile_command.add_argument("--binding", type=Path, required=True)
    compile_command.add_argument("--rules", type=Path, required=True)
    compile_command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "serve":
        from .server import serve
        serve()
        return
    bundle = compile_policy(json.loads(args.binding.read_text()), args.rules.read_text())
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n")
    print("Validated offline policy bundle; semantic equivalence remains unproven.")


if __name__ == "__main__":
    main()
