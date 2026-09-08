"""The persistent mock external world.

Every file under the world directory belongs to an external system, not to this
application.  The application never writes to it; the mock services do, exactly
as the real systems they stand in for would change their own state.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

INVENTORY_DOC = "inventory.json"
SALES_DOC = "sales.json"
CALENDAR_DOC = "calendar.json"
RAW_CALL_DIR = "raw_calls"


def supplier_doc(supplier_id: str) -> str:
    return f"supplier_{supplier_id}.json"


class WorldStore:
    """File-backed access to the mock world directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path(self, name: str) -> Path:
        return self.root / name

    def exists(self, name: str) -> bool:
        return self.path(name).is_file()

    def read(self, name: str) -> dict[str, Any]:
        target = self.path(name)
        if not target.is_file():
            raise FileNotFoundError(f"mock world document not found: {target}")
        with target.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"mock world document {target} must contain an object")
        return data

    def write(self, name: str, data: dict[str, Any]) -> None:
        target = self.path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)

    # -- raw supplier call log -------------------------------------------

    def raw_call_path(self, supplier_id: str) -> Path:
        return self.root / RAW_CALL_DIR / f"{supplier_id}.jsonl"

    def append_raw_call(self, supplier_id: str, entry: dict[str, Any]) -> None:
        target = self.raw_call_path(supplier_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def raw_calls(self, supplier_id: str) -> list[dict[str, Any]]:
        target = self.raw_call_path(supplier_id)
        if not target.is_file():
            return []
        entries: list[dict[str, Any]] = []
        with target.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def iter_supplier_ids(self) -> Iterator[str]:
        for candidate in sorted(self.root.glob("supplier_*.json")):
            yield candidate.stem[len("supplier_") :]
