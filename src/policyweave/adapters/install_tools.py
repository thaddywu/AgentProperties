"""Prepare optional native tools without credentials or shell-profile changes."""

import argparse
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen

from policyweave._paths import cache_directory
from .install_souffle import install as install_souffle
from .model_settings import LOCAL_PROVIDER


CODING_PROVIDERS = {
    "openai": ["codex"], "anthropic": ["claude"], LOCAL_PROVIDER: ["codex"],
    "both": ["codex", "claude"], "none": [],
}


# Pinned official Linux x86_64 releases exercised by the coding adapters.
TOOLS = {
    "codex": dict(
        version="0.164.0",
        url="https://github.com/openai/codex/releases/download/rust-v0.164.0/codex-x86_64-unknown-linux-musl.tar.gz",
        sha256="90dd0b03b28afcb7fa733a4f73b413db2916a47347efd43fb669cc1c774ee8e4",
        member="codex-x86_64-unknown-linux-musl",
        flags=("--ignore-user-config", "--ephemeral", "--json"),
    ),
    "claude": dict(
        version="2.1.252",
        url="https://downloads.claude.ai/claude-code-releases/2.1.252/linux-x64/claude",
        sha256="a715a45105e593fc9808d035d77781f88480b9897975a9df41837f0c591bd4b3",
        flags=("--bare", "--strict-mcp-config", "--no-session-persistence", "--tools"),
    ),
}


def download(url, destination, digest):
    """Verify a bounded download before atomically publishing it."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == digest:
        return destination
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            checksum, size = hashlib.sha256(), 0
            with urlopen(url, timeout=120) as response:
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > 512 * 1024 * 1024:
                        raise ValueError("Tool download exceeds 512 MiB.")
                    checksum.update(block)
                    stream.write(block)
            if checksum.hexdigest() != digest:
                raise ValueError("Tool download checksum mismatch.")
        os.replace(temporary, destination)
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def link_tool(binary, directory, name):
    binary = Path(binary).resolve()
    target = directory / name
    if target.resolve() == binary:
        return
    if target.exists() and not target.is_symlink():
        raise ValueError("An existing environment executable would be replaced: " + name)
    target.unlink(missing_ok=True)
    target.symlink_to(binary)


def coding_ready(binary, name):
    try:
        with Path(binary).open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                return False
        arguments = [str(binary)] + (["exec"] if name == "codex" else []) + ["--help"]
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=30)
        return result.returncode == 0 and all(flag in result.stdout for flag in TOOLS[name]["flags"])
    except (OSError, subprocess.TimeoutExpired):
        return False


def install_coding(name, directory, cache):
    existing = shutil.which(name)
    if existing and coding_ready(Path(existing).resolve(), name):
        link_tool(existing, directory, name)
        return
    spec = TOOLS[name]
    root = cache / name / spec["version"]
    binary = root / name
    if not coding_ready(binary, name):
        artifact = download(spec["url"], root / ("release.tar.gz" if "member" in spec else "release"), spec["sha256"])
        temporary = root / (name + ".new")
        try:
            if "member" in spec:
                with tarfile.open(artifact, "r:gz") as archive:
                    member = archive.getmember(spec["member"])
                    if not member.isfile() or not 0 < member.size <= 512 * 1024 * 1024:
                        raise ValueError("Expected one regular native executable in the release.")
                    with archive.extractfile(member) as source, temporary.open("wb") as output:
                        shutil.copyfileobj(source, output)
            else:
                shutil.copyfile(artifact, temporary)
            temporary.chmod(0o700)
            if not coding_ready(temporary, name):
                raise ValueError("Coding CLI does not support the required isolated-session flags: " + name)
            os.replace(temporary, binary)
        finally:
            temporary.unlink(missing_ok=True)
    link_tool(binary, directory, name)


def engine_ready(binary):
    try:
        result = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=10)
        return result.returncode == 0 and "Version: 2.5" in result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def prepare(provider, directory):
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise ValueError("Automatic native-tool installation supports Linux x86_64; see docs/setup.md.")
    if not shutil.which("prlimit") or not shutil.which("dpkg-deb"):
        raise ValueError("Install util-linux and dpkg before preparing native tools.")
    directory.mkdir(parents=True, exist_ok=True)
    engine = shutil.which("souffle")
    if not engine or not engine_ready(engine):
        root = cache_directory() / "souffle"
        engine = root / "usr/bin/souffle"
        if not engine_ready(engine):
            engine = install_souffle(root)
        if not engine_ready(engine):
            raise ValueError("Souffle cannot start; install the system libraries listed in docs/setup.md.")
    link_tool(engine, directory, "souffle")
    os.environ["PATH"] = str(directory) + os.pathsep + os.environ.get("PATH", "")
    names = CODING_PROVIDERS[provider]
    for name in names:
        install_coding(name, directory, cache_directory() / "coding-tools")
        print(name + " ready")
    from policyweave.core.datalog import Souffle, parse

    rules, _ = parse("Ready(X) :- Probe(X).")
    if not Souffle().evaluate([dict(predicate="Probe", args=["c:ready"])], rules):
        raise ValueError("Native engine self-check failed.")
    print("Native engine ready")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=CODING_PROVIDERS, default="both")
    args = parser.parse_args()
    try:
        prepare(args.provider, Path(sys.executable).parent)
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError):
        parser.exit(1, "Native tool setup failed. See docs/setup.md for manual installation.\n")


if __name__ == "__main__":
    main()
