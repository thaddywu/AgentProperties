"""Create a fresh local workspace without replacing an earlier run."""

import argparse
from datetime import datetime
from pathlib import Path
import re


def create(name, directory, now=None):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("Use an app name with letters, digits, underscores or hyphens.")
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError("The runs directory must not be a symbolic link.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    now = now or datetime.now().astimezone()
    month = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")[now.month - 1]
    stem = f"{now.year}{month}{now:%d_%H%M}_{name}"
    number = 1
    while True:
        target = directory / (stem if number == 1 else f"{stem}_{number:02d}")
        try:
            target.mkdir(mode=0o700)
            return target.resolve()
        except FileExistsError:
            number += 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create a fresh private workspace under runs/.")
    parser.add_argument("name", help="Application name, for example Labcluster")
    args = parser.parse_args(argv)
    try:
        print(create(args.name, Path.cwd() / "runs"))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    return 0
