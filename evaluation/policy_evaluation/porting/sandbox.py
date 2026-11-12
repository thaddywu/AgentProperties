"""One bounded, credential-free container per check or experiment."""

import json
import re
import subprocess
import tempfile
import uuid
from pathlib import Path


class Sandbox:
    def __init__(self, source, candidate, *, image="policy-portin:local", timeout=120):
        self.source, self.candidate = Path(source).resolve(), Path(candidate).resolve()
        # Resolve a tag once so later tag changes cannot silently change the experiment.
        result = subprocess.run(
            ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        self.image = result.stdout.strip()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.image):
            raise ValueError("Expected an immutable local container image identity.")
        # Docker's containerd image store can drop an unreferenced manifest when
        # a mutable build tag moves. Retain an explicit local reference as well.
        self.retained_tag = "policy-portin:retained-" + self.image.removeprefix(
            "sha256:"
        )
        subprocess.run(
            ["docker", "image", "tag", self.image, self.retained_tag],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        self.timeout = timeout

    def run(self, task):
        name = "policy-port-" + uuid.uuid4().hex
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "64",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "--ulimit",
            "fsize=16777216:16777216",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=128m",
            "--user",
            "65534:65534",
            "--mount",
            f"type=bind,source={self.source},target=/application,readonly",
            "--mount",
            f"type=bind,source={self.candidate},target=/candidate,readonly",
            "-i",
            self.image,
        ]
        # No caller environment credentials are forwarded into the container.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            try:
                process = subprocess.run(
                    command,
                    input=json.dumps(task).encode(),
                    stdout=stdout,
                    stderr=stderr,
                    timeout=self.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                subprocess.run(
                    ["docker", "rm", "-f", name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                    check=False,
                )
                return {"passed": False, "error": "Sandbox execution timed out."}
            stdout.seek(0)
            raw = stdout.read(8_388_609)
            if len(raw) > 8_388_608:
                return {
                    "passed": False,
                    "error": "Sandbox output exceeded the record limit.",
                }
            try:
                result = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                stderr.seek(0)
                return {
                    "passed": False,
                    "error": "Sandbox returned no valid result.",
                    "diagnostic": stderr.read(2000).decode(errors="replace"),
                }
            if process.returncode and "error" not in result:
                return {"passed": False, "error": "Sandbox process failed."}
            return result
