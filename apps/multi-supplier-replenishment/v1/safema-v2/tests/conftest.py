from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

INTEGRATION_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = INTEGRATION_ROOT.parent / "base-app"
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
SHARED_ROOT = REPOSITORY_ROOT / "safema-v2"

for path in (SHARED_ROOT, APP_ROOT / "src", APP_ROOT, INTEGRATION_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from replenishment.app import Application  # noqa: E402
from replenishment.domain import OrderRejected  # noqa: E402
from replenishment_safema.integration import install_for_application  # noqa: E402
from tests import support  # noqa: E402


@dataclass
class SafeScenario:
    root: Path
    world: support.World
    config_path: Path
    database_path: Path

    def configure(
        self,
        *,
        hard_max: int = 1000,
        on_hand: int = 0,
        orders_a: list[dict[str, Any]] | None = None,
        orders_b: list[dict[str, Any]] | None = None,
        receipts: list[dict[str, Any]] | None = None,
    ) -> None:
        self.world.write_calendar()
        self.world.write_sales({"SKU-1": support.flat_sales(10)})
        self.world.write_inventory({"SKU-1": on_hand}, receipts=receipts or [])
        self.world.write_supplier(
            "SUPPLIER_A",
            offers={
                "A-1": support.offer(
                    unit_price="1.00",
                    pack_size=10,
                    available_quantity=1000,
                    lead_time_days=2,
                )
            },
            orders=orders_a or [],
        )
        self.world.write_supplier(
            "SUPPLIER_B",
            offers={
                "B-1": support.offer(
                    unit_price="1.10",
                    pack_size=10,
                    available_quantity=1000,
                    lead_time_days=2,
                )
            },
            orders=orders_b or [],
        )
        support.write_config(
            self.config_path,
            world_dir=self.world.root,
            database_path=self.database_path,
            skus=[
                support.sku_config(
                    "SKU-1",
                    hard_max=hard_max,
                    max_unit_price_usd="2.00",
                    autonomous_order_limit_usd="1000.00",
                    mappings={"SUPPLIER_A": "A-1", "SUPPLIER_B": "B-1"},
                )
            ],
        )

    def open_safe(self):
        app = Application.open(self.config_path)
        runtime = install_for_application(
            app,
            owner_config_path=self.config_path,
            metadata_db=self.root / "safema.sqlite3",
        )
        return app, runtime

    def call(
        self,
        app: Application,
        *,
        supplier_id: str = "SUPPLIER_A",
        supplier_sku: str = "A-1",
        quantity: Any = 10,
        price: Any = Decimal("1.00"),
        destination: str = support.DESTINATION,
        key: str = "test/one",
    ):
        return app.services.suppliers[supplier_id].place_order(
            supplier_sku, quantity, price, destination, key
        )

    def mutate_json(self, name: str, mutate) -> None:
        path = self.world.root / name
        document = json.loads(path.read_text(encoding="utf-8"))
        mutate(document)
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def safe_scenario(tmp_path: Path) -> SafeScenario:
    scenario = SafeScenario(
        root=tmp_path,
        world=support.World(tmp_path / "world"),
        config_path=tmp_path / "config.json",
        database_path=tmp_path / "app.sqlite3",
    )
    scenario.configure()
    return scenario
