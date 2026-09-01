"""SQLite schema and connection management.

The database is owned exclusively by the application (specification 7).  No
request source, email gateway, or portal agent ever opens it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Monotonic per-entity counters backing the human-readable record IDs.
CREATE TABLE IF NOT EXISTS counters (
    name  TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS requests (
    request_id              TEXT PRIMARY KEY,
    applicant_name          TEXT NOT NULL,
    application_description TEXT NOT NULL,
    purpose                 TEXT NOT NULL
        CHECK (purpose IN ('PHD_APPLICATION', 'FELLOWSHIP')),
    channel                 TEXT NOT NULL
        CHECK (channel IN ('EMAIL', 'PORTAL')),
    destination             TEXT NOT NULL,
    deadline                TEXT NOT NULL,
    status                  TEXT NOT NULL
        CHECK (status IN ('PENDING', 'SUBMITTED', 'CANCELLED')),
    source_kind             TEXT NOT NULL,
    source_reference        TEXT NOT NULL,
    supersedes_request_id   TEXT REFERENCES requests (request_id),
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    UNIQUE (source_kind, source_reference)
);

CREATE INDEX IF NOT EXISTS idx_requests_pending
    ON requests (status, deadline, request_id);

CREATE TABLE IF NOT EXISTS letters (
    letter_id      TEXT PRIMARY KEY,
    file_path      TEXT NOT NULL,
    applicant_name TEXT NOT NULL,
    purpose        TEXT NOT NULL
        CHECK (purpose IN ('PHD_APPLICATION', 'FELLOWSHIP')),
    registered_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_letters_match
    ON letters (applicant_name, purpose, registered_at, letter_id);

CREATE TABLE IF NOT EXISTS submissions (
    submission_id TEXT PRIMARY KEY,
    request_id    TEXT NOT NULL REFERENCES requests (request_id),
    letter_id     TEXT REFERENCES letters (letter_id),
    attempted_at  TEXT NOT NULL,
    channel       TEXT NOT NULL CHECK (channel IN ('EMAIL', 'PORTAL')),
    outcome       TEXT NOT NULL CHECK (outcome IN ('SUCCEEDED', 'FAILED')),
    receipt       TEXT,
    error_code    TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_submissions_request
    ON submissions (request_id, attempted_at);

CREATE TABLE IF NOT EXISTS reminders (
    reminder_id   TEXT PRIMARY KEY,
    request_id    TEXT NOT NULL REFERENCES requests (request_id),
    reminder_kind TEXT NOT NULL CHECK (reminder_kind IN ('THREE_DAY', 'ONE_DAY')),
    attempted_at  TEXT NOT NULL,
    outcome       TEXT NOT NULL CHECK (outcome IN ('SUCCEEDED', 'FAILED')),
    receipt       TEXT,
    error_code    TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_reminders_request
    ON reminders (request_id, reminder_kind, outcome);

-- Deduplication bookkeeping: an event ID that appears here has already been
-- applied and is ignored on later scans.
CREATE TABLE IF NOT EXISTS applied_events (
    source_kind TEXT NOT NULL,
    event_id    TEXT NOT NULL,
    kind        TEXT NOT NULL,
    applied_at  TEXT NOT NULL,
    PRIMARY KEY (source_kind, event_id)
);
"""


def connect(database_path: str | Path) -> sqlite3.Connection:
    """Open the application database, creating its schema when necessary.

    Transactions are controlled explicitly by the repository, so autocommit
    mode is used at the driver level.
    """
    path = Path(database_path)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    initialize(connection)
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    """Create the schema if it is absent and stamp the schema version."""
    connection.executescript(SCHEMA)
    connection.execute(
        "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT (key) DO NOTHING",
        (SCHEMA_VERSION,),
    )
