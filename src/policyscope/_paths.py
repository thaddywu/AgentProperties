"""Default private state and disposable output paths, outside the source checkout."""

import os
from pathlib import Path


def state_directory():
    return (
        Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
        / "policyscope"
    )


def cache_directory():
    return (
        Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "policyscope"
    )
