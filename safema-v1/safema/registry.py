"""SafeMA-owned generic trusted metadata and decision audit sidecar."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .errors import OriginError
from .types import Context, Effect, Resource

SCHEMA = """
CREATE TABLE IF NOT EXISTS safema_resources (
    binding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_class TEXT NOT NULL,
    identity_json TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    origin_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (object_class, identity_json)
);

CREATE TABLE IF NOT EXISTS safema_contexts (
    context_id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_class TEXT NOT NULL,
    identity_json TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    origin_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (object_class, identity_json)
);

CREATE TABLE IF NOT EXISTS safema_origin_events (
    origin_id TEXT NOT NULL,
    event_identity_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (origin_id, event_identity_json)
);

CREATE TABLE IF NOT EXISTS safema_decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    decided_at TEXT NOT NULL,
    model_id TEXT NOT NULL,
    target TEXT NOT NULL,
    effect_json TEXT,
    observability_json TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('ALLOW', 'DENY')),
    reason TEXT NOT NULL,
    raw_invoked INTEGER NOT NULL DEFAULT 0,
    raw_outcome TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class MetadataRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = str(Path(path))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.executescript(SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self.connection.in_transaction:
            yield
            return
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def bind_resource(self, resource: Resource, *, origin_id: str) -> int:
        identity = canonical_json(resource.identity)
        with self.transaction():
            self.connection.execute(
                "INSERT INTO safema_resources (object_class, identity_json, attributes_json,"
                " origin_id, created_at) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (object_class, identity_json) DO UPDATE SET"
                " attributes_json = excluded.attributes_json, origin_id = excluded.origin_id",
                (
                    resource.object_class,
                    identity,
                    canonical_json(resource.attributes),
                    origin_id,
                    _now(),
                ),
            )
            row = self.connection.execute(
                "SELECT binding_id FROM safema_resources WHERE object_class = ?"
                " AND identity_json = ?",
                (resource.object_class, identity),
            ).fetchone()
        return int(row[0])

    def put_context(self, context: Context, *, origin_id: str) -> int:
        identity = canonical_json(context.identity)
        self.connection.execute(
            "INSERT INTO safema_contexts (object_class, identity_json, attributes_json,"
            " origin_id, updated_at) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT (object_class, identity_json) DO UPDATE SET"
            " attributes_json = excluded.attributes_json, origin_id = excluded.origin_id,"
            " updated_at = excluded.updated_at",
            (
                context.object_class,
                identity,
                canonical_json(context.attributes),
                origin_id,
                _now(),
            ),
        )
        row = self.connection.execute(
            "SELECT context_id FROM safema_contexts WHERE object_class = ?"
            " AND identity_json = ?",
            (context.object_class, identity),
        ).fetchone()
        return int(row[0])

    def patch_context(self, identity: Any, attributes: dict[str, Any]) -> None:
        encoded = canonical_json(identity)
        rows = self.connection.execute(
            "SELECT context_id, attributes_json FROM safema_contexts WHERE identity_json = ?",
            (encoded,),
        ).fetchall()
        if len(rows) != 1:
            raise OriginError(
                f"context identity {identity!r} resolved to {len(rows)} records; expected one"
            )
        merged = json.loads(rows[0]["attributes_json"])
        merged.update(attributes)
        self.connection.execute(
            "UPDATE safema_contexts SET attributes_json = ?, updated_at = ?"
            " WHERE context_id = ?",
            (canonical_json(merged), _now(), rows[0]["context_id"]),
        )

    def all_resources(self) -> list[Resource]:
        rows = self.connection.execute(
            "SELECT * FROM safema_resources ORDER BY binding_id"
        ).fetchall()
        return [
            Resource(
                identity=json.loads(row["identity_json"]),
                object_class=row["object_class"],
                attributes=json.loads(row["attributes_json"]),
            )
            for row in rows
        ]

    def all_contexts(self) -> list[Context]:
        rows = self.connection.execute(
            "SELECT * FROM safema_contexts ORDER BY context_id"
        ).fetchall()
        return [
            Context(
                identity=json.loads(row["identity_json"]),
                object_class=row["object_class"],
                attributes=json.loads(row["attributes_json"]),
            )
            for row in rows
        ]

    def origin_event_seen(self, origin_id: str, identity: Any) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM safema_origin_events WHERE origin_id = ?"
            " AND event_identity_json = ?",
            (origin_id, canonical_json(identity)),
        ).fetchone() is not None

    def record_origin_event(self, origin_id: str, identity: Any) -> None:
        self.connection.execute(
            "INSERT INTO safema_origin_events (origin_id, event_identity_json, observed_at)"
            " VALUES (?, ?, ?)",
            (origin_id, canonical_json(identity), _now()),
        )

    def record_decision(
        self,
        effect: Effect | None,
        *,
        model_id: str,
        target: str,
        observability: dict[str, Any] | None,
        allowed: bool,
        reason: str,
    ) -> int:
        cursor = self.connection.execute(
            "INSERT INTO safema_decisions (decided_at, model_id, target, effect_json,"
            " observability_json, decision, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                _now(),
                model_id,
                target,
                canonical_json(effect.as_dict()) if effect else None,
                canonical_json(observability or {}),
                "ALLOW" if allowed else "DENY",
                reason,
            ),
        )
        return int(cursor.lastrowid)

    def mark_raw_invoked(self, decision_id: int, outcome: str) -> None:
        self.connection.execute(
            "UPDATE safema_decisions SET raw_invoked = 1, raw_outcome = ?"
            " WHERE decision_id = ?",
            (outcome, decision_id),
        )

    def resource_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM safema_resources ORDER BY binding_id"
        ).fetchall()]

    def context_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM safema_contexts ORDER BY context_id"
        ).fetchall()]

    def decisions(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM safema_decisions ORDER BY decision_id"
        ).fetchall()]
