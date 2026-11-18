"""Local workspaces cannot overwrite a previous run or escape through a name."""

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from policyweave.workbench.runs import create


class RunWorkspaceTests(unittest.TestCase):
    def test_repeated_runs_get_distinct_empty_private_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runs"
            now = datetime(2026, 11, 17, 20, 17)
            first = create("Labcluster", root, now)
            (first / "result.json").write_text("retained")
            second = create("Labcluster", root, now)
            self.assertEqual(first.name, "2026Nov17_2017_Labcluster")
            self.assertEqual(second.name, "2026Nov17_2017_Labcluster_02")
            self.assertEqual(list(second.iterdir()), [])
            self.assertEqual((first / "result.json").read_text(), "retained")
            self.assertEqual(second.stat().st_mode & 0o777, 0o700)

    def test_names_and_symlinks_cannot_redirect_the_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("../Other", "/tmp/Other", "", "A/B"):
                with self.assertRaises(ValueError):
                    create(name, root / "runs")
            self.assertFalse((root / "runs").exists())
            (root / "runs").symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                create("Labcluster", root / "runs")
