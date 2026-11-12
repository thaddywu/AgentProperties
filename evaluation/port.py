#!/usr/bin/env python3
"""Checkout launcher for the standalone porting controller."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for directory in ("runtime/python", "translation/python", "query/python", "evaluation"):
    sys.path.insert(0, str(root / directory))

from policy_evaluation.porting.__main__ import main

if __name__ == "__main__":
    main()
