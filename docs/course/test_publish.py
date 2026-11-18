"""Offline publication checks using disposable repositories and fake data."""

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import publish


class CourseReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "source"
        self.root.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Example")
        self.git("config", "user.email", "example@example.invalid")

    def git(self, *args):
        return publish.git(self.root, *args)

    def commit(self, name, content="example\n", executable=False):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        if executable:
            target.chmod(0o755)
        self.git("add", "--", name)
        self.git("commit", "--quiet", "-m", "Add synthetic fixture")

    def test_export_reads_committed_bytes_and_preserves_executable_mode(self):
        self.commit("demo/run.sh", "#!/bin/sh\n", executable=True)
        (self.root / "demo/run.sh").write_text("uncommitted\n")
        (self.root / "demo/connection.yaml").write_text("private placeholder\n")
        output = Path(self.temporary.name) / "export"
        publish.archive(self.root, "HEAD", ("demo",), output)
        self.assertEqual((output / "demo/run.sh").read_text(), "#!/bin/sh\n")
        self.assertTrue((output / "demo/run.sh").stat().st_mode & 0o111)
        self.assertFalse((output / "demo/connection.yaml").exists())

    def test_tracked_private_config_and_links_are_rejected(self):
        for name in ("demo/.env", "demo/connection.yaml", "demo/.review-state/study.json"):
            with self.subTest(name=name):
                self.commit(name)
                with self.assertRaises(ValueError):
                    publish.archive(self.root, "HEAD", (name,), Path(self.temporary.name) / "export")
        self.commit("demo/public.txt")
        (self.root / "demo/link").symlink_to("public.txt")
        self.git("add", "demo/link")
        self.git("commit", "--quiet", "-m", "Add synthetic link")
        with self.assertRaises(ValueError):
            publish.archive(self.root, "HEAD", ("demo/link",), Path(self.temporary.name) / "export")

    def test_clean_check_rejects_tracked_and_untracked_changes(self):
        self.commit("README.md")
        publish.require_clean(self.root)
        (self.root / "untracked.txt").write_text("pending\n")
        with self.assertRaises(ValueError):
            publish.require_clean(self.root)
        (self.root / "untracked.txt").unlink()
        (self.root / "README.md").write_text("pending\n")
        with self.assertRaises(ValueError):
            publish.require_clean(self.root)

    def test_allowlist_excludes_private_submodules_reports_and_repository_config(self):
        self.commit("src/policyweave/__init__.py")
        for name in publish.FILES:
            if name in {"src/policyweave", "tests", "examples", "demo", "docs/design"}:
                name += "/fixture.txt"
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("public fixture\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "Add public export fixtures")
        for name in (".gitmodules", "docs/research/paper.tex", "docs/evaluation/old.md"):
            self.commit(name)
        output = Path(self.temporary.name) / "export"
        publish.archive(self.root, "HEAD", publish.FILES, output)
        self.assertTrue((output / "src/policyweave/__init__.py").exists())
        for name in (".gitmodules", "docs/research", "docs/evaluation"):
            self.assertFalse((output / name).exists())

    def test_publish_replaces_stale_files_without_changing_source_remote(self):
        self.commit("README.md")
        self.git("remote", "add", "origin", "https://example.invalid/development.git")
        destination = Path(self.temporary.name) / "destination.git"
        subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch=main", str(destination)], check=True)
        self.git("push", "--quiet", str(destination), "HEAD:main")
        output = Path(self.temporary.name) / "export"
        output.mkdir()
        (output / "new.txt").write_text("release\n")
        env = {**publish.os.environ, "GIT_AUTHOR_NAME": "Example", "GIT_AUTHOR_EMAIL": "example@example.invalid",
               "GIT_COMMITTER_NAME": "Example", "GIT_COMMITTER_EMAIL": "example@example.invalid"}
        with patch.object(publish, "DESTINATION", str(destination)), patch.dict(publish.os.environ, env):
            publish.publish(self.root, output)
            head = publish.git(destination, "rev-parse", "main")
            publish.publish(self.root, output)
            self.assertEqual(publish.git(destination, "rev-parse", "main"), head)
        self.assertEqual(publish.git(destination, "ls-tree", "--name-only", "main"), b"new.txt\n")
        self.assertEqual(self.git("remote", "get-url", "origin").strip(), b"https://example.invalid/development.git")

    def test_export_builds_pdf_from_pinned_course_sources(self):
        for name in publish.FILES:
            if name in {"src/policyweave", "tests", "examples", "demo", "docs/design"}:
                name += "/fixture.txt"
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("public fixture\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "Add public export fixtures")
        course = self.root / publish.COURSE
        course.mkdir(parents=True)
        publish.git(course, "init", "--quiet")
        publish.git(course, "config", "user.name", "Example")
        publish.git(course, "config", "user.email", "example@example.invalid")
        (course / "images").mkdir()
        (course / "images/example.png").write_bytes(b"synthetic figure")
        (course / "phase2-instructions.tex").write_text(
            "% \\screenshot[height]{name}{caption}\n\\screenshot{example}{Example}\n"
        )
        (course / ".gitignore").write_text("*.pdf\n")
        publish.git(course, "add", ".")
        publish.git(course, "commit", "--quiet", "-m", "Add course fixtures")
        (course / "phase2-instructions.pdf").write_bytes(b"stale local PDF")
        revision = publish.git(course, "rev-parse", "HEAD").decode().strip()
        self.git("update-index", "--add", "--cacheinfo", f"160000,{revision},{publish.COURSE}")
        self.git("commit", "--quiet", "-m", "Pin course revision")
        output = Path(self.temporary.name) / "export"
        original_run = subprocess.run

        def run(command, **kwargs):
            if command[0] != "latexmk":
                return original_run(command, **kwargs)
            self.assertEqual(kwargs["cwd"], output)
            self.assertIn("-no-shell-escape", command)
            build = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("-outdir=")))
            (build / "phase2-instructions.pdf").write_bytes(b"fresh PDF")
            (build / "phase2-instructions.log").write_text("Build complete\n")
            return subprocess.CompletedProcess(command, 0)

        with patch.object(publish.subprocess, "run", side_effect=run):
            publish.export(self.root, output)
        self.assertEqual((output / "phase2-instructions.pdf").read_bytes(), b"fresh PDF")
        self.assertEqual(publish.json.loads((output / "release.json").read_text())["courseCommit"], revision)
        self.assertFalse((output / "docs/course").exists())
        with self.assertRaises(ValueError):
            publish.export(self.root, output)


if __name__ == "__main__":
    unittest.main()
