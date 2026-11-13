"""Exercise the real CLI's default private-state location outside its working tree."""

import json
import os
from pathlib import Path
import select
import stat
import subprocess
import sys
import tempfile
import unittest
from urllib.request import urlopen


class LocalStateTests(unittest.TestCase):
    def test_default_state_is_external_and_explicit_data_takes_precedence(self):
        source = Path(__file__).resolve().parents[1] / "src"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for explicit in (False, True):
                with self.subTest(explicit=explicit):
                    run = root / str(explicit)
                    run.mkdir()
                    checkout = run / "checkout"
                    checkout.mkdir()
                    state = run / "state"
                    selected = run / "chosen"
                    command = [
                        sys.executable,
                        "-B",
                        "-m",
                        "policyscope",
                        "review",
                        "--port",
                        "0",
                    ]
                    if explicit:
                        command += ["--data", str(selected)]
                    process = subprocess.Popen(
                        command,
                        cwd=checkout,
                        env={
                            **os.environ,
                            "PYTHONPATH": str(source),
                            "XDG_STATE_HOME": str(state),
                        },
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    try:
                        ready, _, _ = select.select([process.stdout], [], [], 10)
                        self.assertTrue(ready, "Review server did not start.")
                        line = process.stdout.readline().strip()
                        self.assertTrue(
                            line.startswith("Evaluation UI: http://127.0.0.1:")
                        )
                        with urlopen(
                            line.removeprefix("Evaluation UI: ") + "/api/study",
                            timeout=5,
                        ) as response:
                            self.assertTrue("study" in json.load(response))
                        expected = (
                            selected if explicit else state / "policyscope/default"
                        )
                        record = expected / "study.json"
                        self.assertTrue(record.is_file())
                        self.assertEqual(stat.S_IMODE(record.stat().st_mode) & 0o077, 0)
                        self.assertEqual(list(checkout.iterdir()), [])
                        if explicit:
                            self.assertFalse(state.exists())
                    finally:
                        process.terminate()
                        try:
                            process.communicate(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.communicate()
