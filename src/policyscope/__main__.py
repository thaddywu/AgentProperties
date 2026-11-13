"""Small CLI composition root; optional adapters are loaded only when selected."""

import argparse
import importlib
import sys


COMMANDS = {
    "add": "policyscope.policy_adder.student",
    "translate": "policyscope.policy_adder.__main__",
    "backtranslate": "policyscope.back_translation.__main__",
    "review": "policyscope.workbench.__main__",
    "enforce": "policyscope.enforcement.__main__",
    "analyze": "policyscope.analysis.__main__",
    "run-cases": "policyscope.workbench.cases",
    "pipeline": "policyscope.workbench.pipeline",
    "port-profile": "policyscope.adapters.labcluster.__main__",
}


def main():
    parser = argparse.ArgumentParser(description="PolicyScope policy workflows.")
    parser.add_argument("command", choices=COMMANDS)
    # The selected module owns its complete parser, including --help.
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        parser.parse_args()
        return
    args = parser.parse_args(sys.argv[1:2])
    sys.argv = [f"policyscope {args.command}", *sys.argv[2:]]
    return importlib.import_module(COMMANDS[args.command]).main()


if __name__ == "__main__":
    raise SystemExit(main())
