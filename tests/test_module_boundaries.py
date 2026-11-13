"""Guard the optional-adapter and UI boundary after namespace consolidation."""

import os
from pathlib import Path
import subprocess
import sys
import unittest


class ModuleBoundaryTests(unittest.TestCase):
    def test_reading_analysis_and_execution_import_without_ui_or_model_adapters(self):
        code = """
import importlib.abc
import sys

class RejectOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        blocked = ("policyscope.adapters", "policyscope.workbench", "policyscope.policy_adder", "mcp")
        if any(fullname == name or fullname.startswith(name + ".") for name in blocked):
            raise AssertionError("Core workflow imported an optional boundary: " + fullname)

sys.meta_path.insert(0, RejectOptional())
from policyscope.analysis import QuerySession
from policyscope.back_translation import describe_execution
from policyscope.enforcement import Policy
from policyscope.policy_viewer import review_units
from policyscope.core.policy import CATALOG
assert CATALOG and all(callable(x) for x in (QuerySession, describe_execution, Policy, review_units))
"""
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "PYTHONPATH": str(root / "src")},
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
