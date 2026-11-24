#!/usr/bin/env python3
"""Export committed course files, or publish them to the course repository."""

import argparse
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[2]
COURSE = "docs/phase2-hw-release"
DESTINATION = "git@github.com:thaddywu/CS239-Phase2.git"
FILES = (
    "LICENSE", ".gitattributes", ".gitignore", ".dockerignore", "install.sh", "pyproject.toml",
    "src/policyweave", "tests", "examples", "demo",
    "docs/setup.md", "docs/porting.md", "docs/trajectory.md", "docs/timeline.md",
    "docs/design", "docs/repository-structure.md", "docs/course/README.md",
)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def require_clean(root):
    if git(root, "status", "--porcelain", "--untracked-files=normal").strip():
        raise ValueError("Commit or move pending changes before publishing.")


def archive(root, revision, paths, output):
    data = git(root, "archive", "--format=tar", revision, "--", *paths)
    with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
        for member in bundle:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe archive path.")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("Course exports cannot contain links or special files.")
            if any(part in {".git", ".review-state", "__pycache__", "node_modules"}
                   or part == ".env" or part.startswith(".env.") for part in path.parts):
                raise ValueError("Private or generated files cannot be exported.")
            if path.name in {"connection.yaml", "connection.yml", "connection.json"}:
                if str(path) != "examples/connection.yaml":
                    raise ValueError("Only the public connection template can be exported.")
            target = output / str(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source:
                target.write_bytes(source.read())
            target.chmod(member.mode & 0o777)


def export(root, output):
    require_clean(root)
    source = git(root, "rev-parse", "HEAD").decode().strip()
    course = root / COURSE
    if not (course / ".git").exists():
        raise ValueError("Initialize the course-materials submodule first; see docs/README.md.")
    require_clean(course)
    revision = git(root, "rev-parse", f"{source}:{COURSE}").decode().strip()
    if git(course, "rev-parse", "HEAD").decode().strip() != revision:
        raise ValueError("The course submodule must match the parent commit.")
    if output.exists():
        raise ValueError("The export directory must not already exist.")
    output.mkdir(parents=True)
    archive(root, source, FILES, output)
    shutil.move(output / "docs/course/README.md", output / "README.md")
    (output / "docs/course").rmdir()
    (output / "docs/README.md").write_text(
        "# Documentation\n\n"
        "[Course instructions](../phase2-instructions.pdf) · "
        "[Setup](setup.md) · [Porting](porting.md) · "
        "[Inspector](timeline.md) · [Trajectory contract](trajectory.md)\n"
    )
    archive(course, revision, ("phase2-instructions.tex", "images"), output)
    tex = re.sub(r"(?<!\\)%.*", "", (output / "phase2-instructions.tex").read_text())
    figures = re.findall(r"\\screenshot(?:\[[^\]]*\])?\{([^}]+)\}", tex)
    for figure in figures:
        if not (output / "images" / f"{figure}.png").is_file():
            raise ValueError(f"Missing course figure: {figure}")
    # Build from exactly the exported sources; never reuse a stale local PDF.
    with TemporaryDirectory(prefix="course-pdf-") as build:
        env = {**os.environ, "FORCE_SOURCE_DATE": "1",
               "SOURCE_DATE_EPOCH": git(root, "show", "-s", "--format=%ct", source).decode().strip()}
        result = subprocess.run(
            ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
             "-no-shell-escape", f"-outdir={build}", "phase2-instructions.tex"],
            cwd=output, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        if result.returncode:
            raise ValueError("Course PDF build failed. Run latexmk on the exported source to inspect it.")
        log = (Path(build) / "phase2-instructions.log").read_text(errors="replace")
        if "There were undefined references" in log:
            raise ValueError("Course PDF contains unresolved references.")
        shutil.copyfile(Path(build) / "phase2-instructions.pdf", output / "phase2-instructions.pdf")
    (output / "release.json").write_text(json.dumps(
        {"sourceCommit": source, "courseCommit": revision}, indent=2,
    ) + "\n")


def publish(root, output):
    # Only operate on a disposable clone; the development remote is never changed.
    with TemporaryDirectory(prefix="course-publish-") as temporary:
        checkout = Path(temporary) / "checkout"
        subprocess.run(["git", "clone", "--quiet", "--single-branch", "--branch", "main",
                        DESTINATION, str(checkout)], check=True)
        for entry in checkout.iterdir():
            if entry.name == ".git":
                continue
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        shutil.copytree(output, checkout, dirs_exist_ok=True)
        git(checkout, "add", "--all")
        if not git(checkout, "diff", "--cached", "--name-only").strip():
            print("Course repository is already up to date.")
            return
        print(git(checkout, "diff", "--cached", "--stat").decode(), end="")
        source = git(root, "rev-parse", "--short", "HEAD").decode().strip()
        git(checkout, "commit", "-m", f"Update course release from framework {source}")
        subprocess.run(["git", "-C", str(checkout), "push", "origin", "HEAD:main"], check=True)
        print("Published course release " + git(checkout, "rev-parse", "--short", "HEAD").decode().strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path, help="Build a reviewable export in a new directory")
    mode.add_argument("--push", action="store_true", help="Verify, build and push the course release")
    args = parser.parse_args()
    try:
        if args.push:
            require_clean(ROOT)
            subprocess.run([sys.executable, "-B", "-m", "tests"], cwd=ROOT, check=True)
            with TemporaryDirectory(prefix="course-export-") as temporary:
                output = Path(temporary) / "release"
                export(ROOT, output)
                publish(ROOT, output)
        else:
            export(ROOT, args.output.resolve())
            print("Course export built.")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Release failed: {error}\n")


if __name__ == "__main__":
    main()
