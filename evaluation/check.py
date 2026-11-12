#!/usr/bin/env python3
"""Run the independent Python stack's offline tests; no host workspace or Node."""

from pathlib import Path
import sys
import unittest

root = Path(__file__).resolve().parents[1]
for directory in (
    root / "runtime/python",
    root / "translation/python",
    root / "query/python",
    root / "evaluation",
):
    sys.path.insert(0, str(directory))

suite = unittest.TestSuite()
for directory in (
    root / "translation/python/tests",
    root / "query/python/tests",
    root / "evaluation/tests",
    root / "runtime/python/tests",
):
    suite.addTests(unittest.TestLoader().discover(str(directory), pattern="test_*.py"))
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
