"""Offline checks for downloaded executables and repeatable installation."""

import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from policyweave.adapters import install_tools as tools
from policyweave.adapters import install_souffle


ROOT = Path(__file__).resolve().parents[2]


class NativeToolTests(unittest.TestCase):
    def test_bad_download_never_replaces_existing_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "release"
            target.write_bytes(b"previous")
            with patch.object(tools, "urlopen", return_value=io.BytesIO(b"corrupt")):
                with self.assertRaisesRegex(ValueError, "checksum"):
                    tools.download("https://example.invalid/release", target, "0" * 64)
            self.assertEqual(target.read_bytes(), b"previous")
            self.assertEqual(list(target.parent.iterdir()), [target])

    def test_verified_artifact_is_reused_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "release"
            digest = hashlib.sha256(b"verified").hexdigest()
            with patch.object(tools, "urlopen", return_value=io.BytesIO(b"verified")):
                self.assertEqual(tools.download("https://example.invalid/release", target, digest), target)
            with patch.object(tools, "urlopen", side_effect=AssertionError("Unexpected network")):
                tools.download("https://example.invalid/release", target, digest)
            self.assertEqual(target.read_bytes(), b"verified")

    def test_archive_links_cannot_escape_the_install_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "release.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                member = tarfile.TarInfo(tools.TOOLS["codex"]["member"])
                member.type = tarfile.SYMTYPE
                member.linkname = "../../outside"
                archive.addfile(member)
            binary = root / "codex" / tools.TOOLS["codex"]["version"] / "codex"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"previous")
            with (
                patch.object(tools.shutil, "which", return_value=None),
                patch.object(tools, "coding_ready", return_value=False),
                patch.object(tools, "download", return_value=archive_path),
            ):
                with self.assertRaisesRegex(ValueError, "regular native"):
                    tools.install_coding("codex", root, root)
            self.assertEqual(binary.read_bytes(), b"previous")
            self.assertFalse((root / "outside").exists())
            self.assertFalse(binary.with_name("codex.new").exists())

    def test_native_cli_is_reused_without_replacing_user_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "existing"
            binary.write_bytes(b"native")
            environment = root / "bin"
            environment.mkdir()
            with (
                patch.object(tools.shutil, "which", return_value=str(binary)),
                patch.object(tools, "coding_ready", return_value=True),
                patch.object(tools, "download", side_effect=AssertionError("Unexpected download")),
            ):
                tools.install_coding("claude", environment, root / "cache")
                tools.install_coding("claude", environment, root / "cache")
            self.assertEqual((environment / "claude").resolve(), binary)
            (environment / "claude").unlink()
            (environment / "claude").write_text("user-owned launcher")
            with self.assertRaisesRegex(ValueError, "would be replaced"):
                tools.link_tool(binary, environment, "claude")
            self.assertEqual((environment / "claude").read_text(), "user-owned launcher")

    def test_node_launcher_is_not_mistaken_for_a_standalone_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = Path(directory) / "codex"
            wrapper.write_text("#!/usr/bin/env node\n")
            with patch.object(tools.subprocess, "run", side_effect=AssertionError("Wrapper ran")):
                self.assertFalse(tools.coding_ready(wrapper, "codex"))

    def test_souffle_digest_failure_prevents_extraction(self):
        with (
            patch.object(install_souffle, "urlopen", return_value=io.BytesIO(b"corrupt")),
            patch.object(install_souffle.subprocess, "run") as extract,
        ):
            with self.assertRaisesRegex(ValueError, "digest"):
                install_souffle.install(Path("unused"))
        extract.assert_not_called()


class InstallerJourneyTests(unittest.TestCase):
    def setup_checkout(self, directory):
        root = Path(directory)
        shutil.copyfile(ROOT / "install.sh", root / "install.sh")
        shutil.copyfile(ROOT / "pyproject.toml", root / "pyproject.toml")
        commands = root / "commands"
        commands.mkdir()

        def command(name, body):
            path = commands / name
            path.write_text("#!/bin/bash\nset -eu\n" + body)
            path.chmod(0o700)

        command("uname", 'if [[ $1 == -s ]]; then echo Linux; else echo x86_64; fi\n')
        command("dpkg-query", "echo 'install ok installed'\n")
        command("sudo", 'echo "Unexpected administrator request" >&2; exit 90\n')
        command("python3", '''if [[ $1 == -m && $2 == venv ]]; then
  mkdir -p "$3/bin"
  cat > "$3/bin/python" <<'PYTHON'
#!/bin/bash
printf '%s\\n' "$*" >> "$INSTALL_TEST_LOG"
PYTHON
  chmod +x "$3/bin/python"
fi
''')
        command("docker", '''printf '%s\\n' "$*" >> "$INSTALL_TEST_LOG"
if [[ $1 == info && ${INSTALL_TEST_DOCKER:-ready} != ready ]]; then exit 1; fi
''')
        home = root / "home"
        home.mkdir()
        config = home / ".config/policyweave/connection.yaml"
        config.parent.mkdir(parents=True)
        config.write_text('provider: openai\nopenai:\n  apiKey: "synthetic-existing-key"\n')
        env = {**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"],
               "HOME": str(home), "INSTALL_TEST_LOG": str(root / "commands.log")}
        return root, config, env

    def test_repeat_install_skips_python_install_and_preserves_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            root, config, env = self.setup_checkout(directory)
            original = config.read_bytes()
            for _ in range(2):
                result = subprocess.run(["bash", "install.sh"], cwd=root, env=env,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
            commands = (root / "commands.log").read_text()
            self.assertEqual(commands.count("-m pip install"), 1)
            self.assertEqual(commands.count("policyweave.adapters.install_tools --provider both"), 2)
            self.assertEqual(config.read_bytes(), original)
            self.assertNotIn("synthetic-existing-key", result.stdout + result.stderr + commands)

    def test_unavailable_docker_stops_before_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root, config, env = self.setup_checkout(directory)
            env["INSTALL_TEST_DOCKER"] = "unavailable"
            result = subprocess.run(["bash", "install.sh"], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Start Docker", result.stderr)
            self.assertFalse((root / ".venv").exists())
            self.assertTrue(config.is_file())

    def test_local_option_prepares_codex_and_preserves_connection(self):
        from policyweave.adapters.model_settings import LOCAL_PROVIDER

        self.assertEqual(tools.CODING_PROVIDERS[LOCAL_PROVIDER], ["codex"])
        with tempfile.TemporaryDirectory() as directory:
            root, config, env = self.setup_checkout(directory)
            original = config.read_bytes()
            result = subprocess.run(["bash", "install.sh", "--provider", LOCAL_PROVIDER],
                                    cwd=root, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("policyweave.adapters.install_tools --provider " + LOCAL_PROVIDER,
                          (root / "commands.log").read_text())
            self.assertEqual(config.read_bytes(), original)

    def test_invalid_provider_stops_before_any_environment_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, env = self.setup_checkout(directory)
            result = subprocess.run(["bash", "install.sh", "--provider", "invalid"],
                                    cwd=root, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((root / "commands.log").exists())
            self.assertFalse((root / ".venv").exists())
