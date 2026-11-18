"""Small CLI composition root; optional adapters are loaded only when selected."""

import argparse
import importlib
import sys


COMMANDS = {
    "port": "policyweave.workbench.port",
    "translate-harness": "policyweave.workbench.translate_harness",
    "back-translate": "policyweave.workbench.back_translate",
    "add": "policyweave.policy_adder.student",
    "translate": "policyweave.policy_adder.__main__",
    "backtranslate": "policyweave.back_translation.__main__",
    "review": "policyweave.workbench.__main__",
    "view-translation": "policyweave.workbench.__main__",
    "enforce": "policyweave.enforcement.__main__",
    "analyze": "policyweave.analysis.__main__",
    "inspect": "policyweave.workbench.analysis",
    "run-cases": "policyweave.workbench.cases",
    "pipeline": "policyweave.workbench.pipeline",
}


def main():
    parser = argparse.ArgumentParser(description="PolicyWeave policy workflows.")
    parser.add_argument("command", choices=COMMANDS)
    # The selected module owns its complete parser, including --help.
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        parser.parse_args()
        return
    args = parser.parse_args(sys.argv[1:2])
    sys.argv = [f"policyweave {args.command}", *sys.argv[2:]]
    return importlib.import_module(COMMANDS[args.command]).main()


if __name__ == "__main__":
    raise SystemExit(main())
