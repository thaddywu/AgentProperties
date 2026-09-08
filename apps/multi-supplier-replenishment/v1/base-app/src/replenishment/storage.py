"""SQLite persistence for application-owned records only.

Deleting or recreating this database never changes inventory, sales, calendar,
or supplier state; those live in their own authoritative systems.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "1"

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id           TEXT PRIMARY KEY,
        run_seq          INTEGER NOT NULL UNIQUE,
        trigger_kind     TEXT NOT NULL,
        business_date    TEXT NOT NULL,
        started_at       TEXT NOT NULL,
        ended_at         TEXT,
        status           TEXT NOT NULL,
        source_snapshots TEXT NOT NULL DEFAULT '{}',
        note             TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ux_runs_scheduled_business_date
        ON runs (business_date) WHERE trigger_kind = 'SCHEDULED'
    """,
    """
    CREATE TABLE IF NOT EXISTS run_events (
        event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      TEXT NOT NULL REFERENCES runs (run_id),
        occurred_at TEXT NOT NULL,
        category    TEXT NOT NULL,
        message     TEXT NOT NULL,
        detail      TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sku_decisions (
        decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      TEXT NOT NULL REFERENCES runs (run_id),
        sku         TEXT NOT NULL,
        outcome     TEXT NOT NULL,
        reason      TEXT NOT NULL DEFAULT '',
        detail      TEXT NOT NULL DEFAULT '{}',
        recorded_at TEXT NOT NULL,
        UNIQUE (run_id, sku)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_attempts (
        attempt_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id              TEXT NOT NULL REFERENCES runs (run_id),
        sku                 TEXT NOT NULL,
        supplier_id         TEXT NOT NULL,
        supplier_sku        TEXT NOT NULL,
        destination_id      TEXT NOT NULL,
        quantity            INTEGER NOT NULL,
        expected_unit_price TEXT NOT NULL,
        total_cost          TEXT NOT NULL,
        idempotency_key     TEXT NOT NULL UNIQUE,
        state               TEXT NOT NULL,
        supplier_order_id   TEXT,
        reason              TEXT NOT NULL DEFAULT '',
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL,
        UNIQUE (run_id, sku)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reconciliation_events (
        event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        attempt_id      INTEGER NOT NULL REFERENCES purchase_attempts (attempt_id),
        run_id          TEXT,
        occurred_at     TEXT NOT NULL,
        lookup_outcome  TEXT NOT NULL,
        resulting_state TEXT NOT NULL,
        detail          TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS recorded_supplier_orders (
        supplier_id            TEXT NOT NULL,
        supplier_order_id      TEXT NOT NULL,
        idempotency_key        TEXT,
        destination_id         TEXT NOT NULL,
        supplier_sku           TEXT NOT NULL,
        store_sku              TEXT,
        quantity               INTEGER NOT NULL,
        unit_price             TEXT NOT NULL,
        total_cost             TEXT NOT NULL,
        observed_status        TEXT NOT NULL,
        created_at             TEXT NOT NULL,
        promised_delivery_date TEXT,
        observed_at            TEXT NOT NULL,
        source                 TEXT NOT NULL,
        PRIMARY KEY (supplier_id, supplier_order_id)
    )
    """,
)


def connect(database_path: str | Path) -> sqlite3.Connection:
    """Open the application database with foreign keys and row access by name."""
    path = Path(database_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    """Create the schema explicitly at startup."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (SCHEMA_VERSION,),
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
