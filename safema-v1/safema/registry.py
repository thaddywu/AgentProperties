"""Persistent SafeMA-owned trusted metadata and decision audit registry."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from .types import NormalizedEffect, ResourceMetadata

SCHEMA = """
CREATE TABLE IF NOT EXISTS resource_versions (
    binding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    resolver_id TEXT NOT NULL,
    resource_class TEXT NOT NULL,
    canonical_path TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    principal TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    origin_id TEXT NOT NULL,
    application_resource_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (resolver_id, canonical_path, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_resource_path
    ON resource_versions (resolver_id, canonical_path);

CREATE TABLE IF NOT EXISTS destination_contexts (
    context_key TEXT PRIMARY KEY,
    principal TEXT NOT NULL,
    channel TEXT NOT NULL,
    allowed_destinations_json TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('active', 'inactive')),
    origin_id TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observed_origin_events (
    origin_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    event_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (origin_id, source_kind, event_id)
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    decided_at TEXT NOT NULL,
    model_id TEXT NOT NULL,
    target TEXT NOT NULL,
    effect_json TEXT,
    decision TEXT NOT NULL CHECK (decision IN ('ALLOW', 'DENY')),
    reason TEXT NOT NULL,
    raw_invoked INTEGER NOT NULL DEFAULT 0,
    raw_outcome TEXT
);
"""


def now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fingerprint(path: str) -> tuple[str, str]:
    canonical = str(Path(path).expanduser().resolve(strict=True))
    digest = hashlib.sha256()
    with open(canonical, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return canonical, digest.hexdigest()


class MetadataRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = str(Path(path))
        parent = Path(self.path).parent
        parent.mkdir(parents=True, exist_ok=True)
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

    def bind_resource(
        self,
        *,
        resolver_id: str,
        resource_class: str,
        path: str,
        principal: str,
        attributes: dict[str, Any],
        origin_id: str,
        application_resource_id: Optional[str],
    ) -> int:
        canonical, digest = fingerprint(path)
        with self.transaction():
            self.connection.execute(
                "INSERT INTO resource_versions (resolver_id, resource_class,"
                " canonical_path, fingerprint, principal, attributes_json, origin_id,"
                " application_resource_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (resolver_id, canonical_path, fingerprint) DO UPDATE SET"
                " principal = excluded.principal, attributes_json = excluded.attributes_json,"
                " origin_id = excluded.origin_id,"
                " application_resource_id = excluded.application_resource_id",
                (
                    resolver_id,
                    resource_class,
                    canonical,
                    digest,
                    principal,
                    json.dumps(attributes, sort_keys=True),
                    origin_id,
                    application_resource_id,
                    now_text(),
                ),
            )
            row = self.connection.execute(
                "SELECT binding_id FROM resource_versions WHERE resolver_id = ?"
                " AND canonical_path = ? AND fingerprint = ?",
                (resolver_id, canonical, digest),
            ).fetchone()
        return int(row[0])

    def resolve_resource(
        self, *, resolver_id: str, resource_class: str, path: str
    ) -> tuple[Optional[ResourceMetadata], str]:
        try:
            canonical, digest = fingerprint(path)
        except (OSError, ValueError) as exc:
            return None, f"resource unavailable: {exc}"
        row = self.connection.execute(
            "SELECT * FROM resource_versions WHERE resolver_id = ?"
            " AND resource_class = ? AND canonical_path = ? AND fingerprint = ?",
            (resolver_id, resource_class, canonical, digest),
        ).fetchone()
        if row is None:
            prior = self.connection.execute(
                "SELECT 1 FROM resource_versions WHERE resolver_id = ? AND canonical_path = ?",
                (resolver_id, canonical),
            ).fetchone()
            if prior:
                return None, "registered path has a different content fingerprint"
            return None, "no trusted binding for resource"
        return (
            ResourceMetadata(
                binding_id=int(row["binding_id"]),
                resolver_id=row["resolver_id"],
                resource_class=row["resource_class"],
                canonical_path=row["canonical_path"],
                fingerprint=row["fingerprint"],
                principal=row["principal"],
                attributes=json.loads(row["attributes_json"]),
            ),
            "resolved",
        )

    @staticmethod
    def context_key(source_kind: str, source_reference: str) -> str:
        return json.dumps([source_kind, source_reference], separators=(",", ":"))

    def origin_event_seen(self, origin_id: str, source_kind: str, event_id: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM observed_origin_events WHERE origin_id = ?"
            " AND source_kind = ? AND event_id = ?",
            (origin_id, source_kind, event_id),
        ).fetchone() is not None

    def record_origin_event(self, origin_id: str, source_kind: str, event_id: str) -> None:
        self.connection.execute(
            "INSERT INTO observed_origin_events (origin_id, source_kind, event_id, observed_at)"
            " VALUES (?, ?, ?, ?)",
            (origin_id, source_kind, event_id, now_text()),
        )

    def activate_context(
        self,
        *,
        context_key: str,
        principal: str,
        channel: str,
        allowed_destinations: list[str],
        attributes: dict[str, Any],
        origin_id: str,
    ) -> None:
        self.connection.execute(
            "INSERT INTO destination_contexts (context_key, principal, channel,"
            " allowed_destinations_json, attributes_json, state, origin_id, updated_at)"
            " VALUES (?, ?, ?, ?, ?, 'active', ?, ?)"
            " ON CONFLICT (context_key) DO UPDATE SET principal = excluded.principal,"
            " channel = excluded.channel,"
            " allowed_destinations_json = excluded.allowed_destinations_json,"
            " attributes_json = excluded.attributes_json, state = 'active',"
            " origin_id = excluded.origin_id, updated_at = excluded.updated_at",
            (
                context_key,
                principal,
                channel,
                json.dumps(sorted(set(allowed_destinations))),
                json.dumps(attributes, sort_keys=True),
                origin_id,
                now_text(),
            ),
        )

    def deactivate_context(self, context_key: str) -> None:
        self.connection.execute(
            "UPDATE destination_contexts SET state = 'inactive', updated_at = ?"
            " WHERE context_key = ?",
            (now_text(), context_key),
        )

    def matching_contexts(
        self, *, principal: str, channel: str, actual_destinations: set[str]
    ) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM destination_contexts WHERE principal = ? AND channel = ?"
            " AND state = 'active'",
            (principal, channel),
        ).fetchall()
        matches = []
        for row in rows:
            allowed = set(json.loads(row["allowed_destinations_json"]))
            if actual_destinations and actual_destinations.issubset(allowed):
                matches.append(
                    {
                        "context_key": row["context_key"],
                        "principal": row["principal"],
                        "channel": row["channel"],
                        "allowed_destinations": sorted(allowed),
                        "attributes": json.loads(row["attributes_json"]),
                    }
                )
        return matches

    def record_decision(
        self, effect: Optional[NormalizedEffect], *, model_id: str, target: str,
        allowed: bool, reason: str
    ) -> int:
        cursor = self.connection.execute(
            "INSERT INTO decisions (decided_at, model_id, target, effect_json, decision,"
            " reason) VALUES (?, ?, ?, ?, ?, ?)",
            (
                now_text(),
                model_id,
                target,
                json.dumps(effect.as_dict(), sort_keys=True) if effect else None,
                "ALLOW" if allowed else "DENY",
                reason,
            ),
        )
        return int(cursor.lastrowid)

    def mark_raw_invoked(self, decision_id: int, outcome: str) -> None:
        self.connection.execute(
            "UPDATE decisions SET raw_invoked = 1, raw_outcome = ? WHERE decision_id = ?",
            (outcome, decision_id),
        )

    def decisions(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM decisions ORDER BY decision_id"
        ).fetchall()]
    def resources(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM resource_versions ORDER BY binding_id"
        ).fetchall()]

    def contexts(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM destination_contexts ORDER BY context_key"
        ).fetchall()]
