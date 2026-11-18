"""Bounded immutable artifact reads and private atomic writes."""

from pathlib import Path
import hashlib
import json
import os
import uuid


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with temporary.open("x", encoding="utf-8") as stream:
        temporary.chmod(0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
    os.replace(temporary, path)


def artifact_text(root, relative, *, max_bytes=4_000_000):
    if Path(root).is_symlink():
        raise ValueError("Artifact workspace must not be a symbolic link.")
    root, path = Path(root).resolve(), Path(root) / relative
    if (
        path.is_symlink()
        or not path.resolve().is_relative_to(root)
        or not path.is_file()
        or path.stat().st_size > max_bytes
    ):
        raise ValueError(
            "Generated artifact must be a bounded regular file inside its workspace."
        )
    return path.read_text()


def files(directory):
    return {
        str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in directory.rglob("*")
        if p.is_file()
        and not p.is_symlink()
        and not set(p.relative_to(directory).parts) & {".git", "__pycache__"}
    }
