"""Wiring of configuration, adapters, database, and engine."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from .adapters.registry import Services, build_services
from .config import Config, load_config
from .engine import ReplenishmentEngine
from .errors import RunLockError
from .journal import Journal
from .locking import RunLock
from .storage import connect, migrate


@dataclass
class Application:
    config: Config
    services: Services
    connection: sqlite3.Connection
    journal: Journal
    engine: ReplenishmentEngine
    recovered: dict[str, list[str]]

    @classmethod
    def open(
        cls,
        config_path: str | Path,
        *,
        create_schema: bool = True,
        recover: bool = True,
    ) -> "Application":
        config = load_config(config_path)
        services = build_services(config)
        connection = connect(config.database_path)
        if create_schema:
            migrate(connection)
        journal = Journal(connection)
        lock = RunLock(str(config.database_path) + ".lock")
        recovered: dict[str, list[str]] = {"runs": [], "attempts": []}
        if recover:
            # Only a worker that can take the exclusive lock may declare an
            # interrupted run dead; another live worker must not be disturbed.
            try:
                lock.acquire()
            except RunLockError:
                pass
            else:
                try:
                    recovered = journal.recover_interrupted(services.clock.now())
                finally:
                    lock.release()
        engine = ReplenishmentEngine(config, services, journal, lock)
        return cls(
            config=config,
            services=services,
            connection=connection,
            journal=journal,
            engine=engine,
            recovered=recovered,
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Application":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
