"""Read a selected installed app, then align frozen descriptions separately."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

from policyweave.core.artifacts import files, save
from policyweave.core.policy import fingerprint
from policyweave.adapters.model_settings import CONNECTION_FILENAMES
from policyweave.policy_adder.codex import CodexPort, EXCLUDED, EXTENSIONS, PACKAGE, copy_runtime
from policyweave.policy_adder.student import load_connection, write_bundle


def run(application, policy, output, settings, *, work=None,
        image="policy-portin:batch-v1", codex="codex", progress=None):
    application, policy = Path(application).resolve(), Path(policy).resolve()
    output = Path(output).absolute()
    if not application.is_dir() or not (application / "policy_port/rules.dl").is_file():
        raise ValueError("Ported app requires policy_port/rules.dl.")
    if not policy.is_file():
        raise ValueError("Original policy must be a readable Markdown file.")
    if output.is_symlink() or (output.exists() and (
        not output.is_dir() or any(output.iterdir())
    )):
        raise ValueError("Back-translation output directory must be absent or empty.")
    output = output.resolve()
    if application.is_relative_to(output.resolve()):
        raise ValueError("Output must not contain the ported application.")
    if policy.is_relative_to(output.resolve()):
        raise ValueError("Output must not contain the original policy.")
    work = Path(work).absolute() if work else output.parent / ("." + output.name + ".reading")
    for protected in (application, output.resolve(), policy):
        if work.resolve().is_relative_to(protected) or protected.is_relative_to(work.resolve()):
            raise ValueError("Keep private work separate from app, policy and output.")
    port = CodexPort(work, settings, image=image, codex=codex)
    work.mkdir(parents=True, mode=0o700, exist_ok=False)
    candidate = work / "candidate"
    candidate.mkdir()
    # Snapshot code/configuration only. Never follow links into other workspaces.
    for path in application.rglob("*"):
        relative = path.relative_to(application)
        if set(relative.parts) & (EXCLUDED | {"back-translation", ".review-state"}):
            continue
        if path.is_symlink():
            raise ValueError("Ported implementation must not contain symbolic links.")
        if (not path.is_file() or path.suffix not in EXTENSIONS or path.resolve() == policy
                or path.name.lower() in CONNECTION_FILENAMES
                or path.name == "review.json" or path.resolve().is_relative_to(output.resolve())):
            continue
        destination = candidate / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    # The original policy exists only in the alignment workspace. The independent
    # reader receives a separately filtered implementation-only evidence bundle.
    text = policy.read_text(encoding="utf-8")
    original = work / "original"
    original.mkdir()
    (original / "policy.md").write_text(text, encoding="utf-8")
    save(work / "source.json", dict(
        policy="policy.md", revision=fingerprint(files(candidate)), files=files(original),
    ))
    runtime = work / "framework/policyweave"
    copy_runtime(PACKAGE, runtime)
    port.runtime = runtime
    if progress:
        progress("independent-back-translation")
    result = port.backtranslate()
    if not result.get("passed"):
        raise ValueError("Independent reading failed; private evidence retained.")
    if progress:
        progress("policy-viewer-alignment")
    port.review()
    clean = work / ("bundle-" + uuid.uuid4().hex[:12])
    # Compute the final relative app pointer, although the bundle is staged first.
    write_bundle(port, clean, application, text, portable=True)
    manifest = json.loads((clean / "manifest.json").read_text())
    manifest.pop("id")
    manifest["applicationPath"] = os.path.relpath(application, output)
    manifest["id"] = fingerprint(manifest)
    save(clean / "manifest.json", manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or (output.exists() and (
        not output.is_dir() or any(output.iterdir())
    )):
        raise ValueError("Output became nonempty; private results retained.")
    os.rename(clean, output)
    return output


def main():
    parser = argparse.ArgumentParser(description="Independently read a ported app and align its original policy.")
    parser.add_argument("--ported-app", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--connection", required=True, type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--image", default="policy-portin:batch-v1")
    parser.add_argument("--codex", default="codex")
    args = parser.parse_args()
    try:
        target = run(args.ported_app, args.policy, args.output,
                     load_connection(args.connection), work=args.work_dir,
                     image=args.image, codex=args.codex,
                     progress=lambda stage: print(stage, flush=True))
        print("Execution reading: " + str(target))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
