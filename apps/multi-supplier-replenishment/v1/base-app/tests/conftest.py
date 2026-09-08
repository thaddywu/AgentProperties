"""Shared pytest fixtures.

Every test builds its own mock world and its own application database inside a
temporary directory.  Time is injected through the configured fixed clock, so
no assertion depends on the wall clock, the machine locale, or test order.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(SRC))

from replenishment.app import Application  # noqa: E402
from replenishment.domain import TriggerKind  # noqa: E402
from replenishment.engine import RunOutcome  # noqa: E402

from . import support  # noqa: E402


@dataclass
class Scenario:
    root: Path
    world: support.World
    config_path: Path
    database_path: Path

    def configure(
        self,
        skus: Iterable[Mapping[str, Any]],
        **overrides: Any,
    ) -> Path:
        return support.write_config(
            self.config_path,
            world_dir=self.world.root,
            database_path=self.database_path,
            skus=skus,
            **overrides,
        )

    def set_instant(self, instant: str) -> None:
        document = json.loads(self.config_path.read_text(encoding="utf-8"))
        document["adapters"]["clock"]["options"]["instant"] = instant
        self.config_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    def open(self, **kwargs: Any) -> Application:
        return Application.open(self.config_path, **kwargs)

    def run(self, trigger: TriggerKind = TriggerKind.MANUAL, **kwargs: Any) -> RunOutcome:
        with self.open(**kwargs) as app:
            return app.engine.execute(trigger)


@pytest.fixture
def scenario(tmp_path: Path) -> Scenario:
    return Scenario(
        root=tmp_path,
        world=support.World(tmp_path / "world"),
        config_path=tmp_path / "config.json",
        database_path=tmp_path / "state" / "app.sqlite3",
    )


@pytest.fixture
def simple_world(scenario: Scenario) -> Scenario:
    """One SKU, both suppliers offering, a flat all-NORMAL demand history."""
    scenario.world.write_calendar()
    scenario.world.write_sales({"SKU-1": support.flat_sales(10)})
    scenario.world.write_inventory({"SKU-1": 0})
    scenario.world.write_supplier(
        "SUPPLIER_A",
        offers={"A-1": support.offer(unit_price="1.00", pack_size=10, lead_time_days=2)},
    )
    scenario.world.write_supplier(
        "SUPPLIER_B",
        offers={"B-1": support.offer(unit_price="1.10", pack_size=10, lead_time_days=2)},
    )
    scenario.configure(
        [
            support.sku_config(
                "SKU-1",
                mappings={"SUPPLIER_A": "A-1", "SUPPLIER_B": "B-1"},
            )
        ]
    )
    return scenario
