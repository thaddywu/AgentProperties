"""Small deterministic sink used to test API models independently of RecSub."""

from __future__ import annotations

from typing import Any


class RecordingDisclosureSink:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def disclose(self, *, file_path: str, destination: str) -> bool:
        self.calls.append({"file_path": file_path, "destination": destination})
        return True
