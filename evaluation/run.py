#!/usr/bin/env python3
"""Checkout launcher; equivalent to policy-evaluate after installing the four packages."""

from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
for directory in (
    root / "runtime/python",
    root / "translation/python",
    root / "query/python",
    root / "evaluation",
):
    sys.path.insert(0, str(directory))

from policy_evaluation.__main__ import main

if __name__ == "__main__":
    main()
