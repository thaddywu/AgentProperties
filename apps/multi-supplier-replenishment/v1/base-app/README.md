# Multi-Supplier Replenishment Automation

A local, deterministic replenishment application for one independently
operated urban convenience store. Once per local business day it reads
authoritative inventory, sales, calendar, and supplier state; forecasts
near-term demand for the configured shelf-stable SKUs; decides whether and how
much to replenish; picks one of two approved suppliers; and places purchase
orders that stay inside the owner's configured purchasing limits.

It uses no LLM, no agent framework, no hosted service, and no network. Every
external system sits behind an explicit interface with a complete local
implementation, so the whole application is runnable and demonstrable offline.

* Python 3.11 or newer
* Standard library only at runtime (`pytest` is the sole development dependency)
* SQLite for application-owned records

---

## 1. Setting up a development environment

Everything below is run from this directory (`base-app/`).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the `replenishment` package and the `replenish` command.

## 2. Running the tests

```bash
pytest
```

The suite is fully deterministic and offline: it injects time through a fixed
clock, builds its own mock world in a temporary directory, and asserts exact
supplier call counts and arguments. It never touches the network, the wall
clock, the machine locale, or a random identifier.

## 3. Initializing a fresh database and mock world

The committed example lives in [`fixtures/`](fixtures/). Copy it into a working
directory (`state/`) so the committed fixtures stay pristine:

```bash
replenish --config fixtures/config.example.json init-world
replenish --config fixtures/config.example.json init-db
```

* `init-world` copies `fixtures/world/` into the `world_dir` named by the
  configuration (`state/world/`). It refuses to overwrite existing world state
  unless you pass `--force`.
* `init-db` creates the application SQLite schema at `state/app.sqlite3`.

Both write only inside `base-app/`.

## 4. Running one manual replenishment cycle

```bash
replenish --config fixtures/config.example.json run
```

Add `--json` for the machine-readable form. The example configuration uses a
**fixed clock** pinned to `2026-09-03T09:05:00Z` (05:05 in
`America/New_York`), which makes the demonstration reproducible. For real
operation, change the clock adapter to:

```json
"clock": { "factory": "system_clock", "options": {} }
```

The first run over the committed fixtures produces every documented outcome:

| SKU | Outcome | What it demonstrates |
|---|---|---|
| `SKU-CHIPS-BBQ-150G` | `ORDER_ACCEPTED` | a normal accepted replenishment order |
| `SKU-COFFEE-CUP-12OZ` | `ORDER_ACCEPTED` | Supplier A unavailable, Supplier B still usable |
| `SKU-WATER-500ML` | `NO_ORDER_NEEDED` | a delivered order already matched by a ledger receipt |
| `SKU-SODA-CAN-330` | `NO_ORDER_NEEDED` | an externally created, manually placed outstanding order |
| `SKU-CANDY-BAR-45G` | `NO_ORDER_NEEDED` | a `DELIVERED` order still awaiting its ledger receipt |
| `SKU-ENERGY-16OZ` | `ESCALATION_REQUIRED` | the per-order autonomous spend limit |
| `SKU-JUICE-1L` | `ESCALATION_REQUIRED` | the hard inventory-exposure maximum |
| `SKU-GUM-PACK-10` | `SUPPLIER_REJECTED` | a definitive supplier rejection, with no fallback |
| `SKU-NUTS-MIX-90G` | `ORDER_OUTCOME_UNKNOWN` | a response lost after dispatch |

## 5. Starting the scheduler

```bash
replenish --config fixtures/config.example.json scheduler
```

The scheduler polls (default every 30 s), runs once when the configured local
run time (05:00 store time) is reached, catches up once on startup if that
local date has no scheduled run yet, and does nothing more for a date whose
scheduled run already exists. A failed or interrupted scheduled run is never
retried automatically — inspect it and start a manual run instead.

`--max-cycles N` stops after N polling cycles, which is what you want with the
example's fixed clock:

```bash
replenish --config fixtures/config.example.json scheduler --max-cycles 1
```

Nothing here contacts an external service: every adapter reads and writes the
local mock world directory.

## 6. Inspecting what happened

```bash
# scheduler status, the active run, the last completed run, open attempts
replenish --config fixtures/config.example.json status

# runs, newest first
replenish --config fixtures/config.example.json runs

# one run with its source snapshots, events, decisions, and attempts
replenish --config fixtures/config.example.json show-run RUN-000001

# per-SKU decisions and the inputs behind them
replenish --config fixtures/config.example.json decisions --run RUN-000001
replenish --config fixtures/config.example.json decisions --sku SKU-JUICE-1L

# purchase attempts with their reconciliation history
replenish --config fixtures/config.example.json attempts
replenish --config fixtures/config.example.json attempts --state OUTCOME_UNKNOWN

# supplier order IDs and the statuses this application observed
replenish --config fixtures/config.example.json orders --sku SKU-CHIPS-BBQ-150G

# the mock world's raw supplier call log
replenish --config fixtures/config.example.json supplier-calls --supplier SUPPLIER_A
```

Every command accepts `--json`. Reports distinguish zero, missing, rejected,
unavailable, malformed, and unknown values, and never show a proposed or
dispatched order as accepted.

The raw call log is also a plain file you can read directly:

```bash
cat state/world/raw_calls/SUPPLIER_A.jsonl
```

## 7. Reproducing an unknown outcome and reconciling it

The committed world tells Supplier A to lose the response for
`A-NUTS-MIX-90G` exactly once
(`place_order_behaviors` in `fixtures/world/supplier_SUPPLIER_A.json`).

```bash
# 1. The first run dispatches, loses the response, and refuses to guess.
replenish --config fixtures/config.example.json run
replenish --config fixtures/config.example.json attempts --state OUTCOME_UNKNOWN

# 2. The supplier really did create the order; look at its own state.
grep -n "A-NUTS-MIX-90G" state/world/supplier_SUPPLIER_A.json

# 3. The next run reconciles by idempotency key before planning anything.
replenish --config fixtures/config.example.json run
replenish --config fixtures/config.example.json attempts --run RUN-000001
```

The attempt moves from `OUTCOME_UNKNOWN` to `ACCEPTED` with the supplier's own
order ID, the recovered order counts toward outstanding quantity in that same
run, and no second order is ever created.

To see a SKU stay blocked instead, start from a fresh world and make the
supplier unable to decide the lookup:

```bash
replenish --config fixtures/config.example.json init-world --force
rm -f state/app.sqlite3*
replenish --config fixtures/config.example.json init-db

python3 - <<'PYEOF'
import json, pathlib
path = pathlib.Path("state/world/supplier_SUPPLIER_A.json")
world = json.loads(path.read_text())
world["lookup_behaviors"]["*"] = ["unknown"]
path.write_text(json.dumps(world, indent=2))
PYEOF

replenish --config fixtures/config.example.json run          # RUN-000001
replenish --config fixtures/config.example.json run          # RUN-000002
replenish --config fixtures/config.example.json decisions \
    --run RUN-000002 --sku SKU-NUTS-MIX-90G
```

The SKU is reported as `BLOCKED_UNKNOWN_ATTEMPT`; the application does not
retry it, does not mint a new key, and does not switch suppliers. Only that
SKU is blocked — the others are planned normally.

## 8. Resetting or copying state

All of these stay inside `base-app/`.

```bash
# start the mock world again from the committed fixtures
replenish --config fixtures/config.example.json init-world --force

# throw away only the application's own records
rm -f state/app.sqlite3 state/app.sqlite3-wal state/app.sqlite3-shm state/app.sqlite3.lock
replenish --config fixtures/config.example.json init-db

# keep a copy of a world you want to come back to
cp -r state/world state/world-backup

# copy the example into a scratch world of your own
replenish --config fixtures/config.example.json init-world \
    --source fixtures/world --force
```

Deleting or recreating the application database never changes inventory,
sales, calendar, or supplier state: those live in the mock world files and,
in production, in the real external systems.

---

## What belongs to whom

| Data | Owner | Where it lives here |
|---|---|---|
| SKU identity, base unit, active flag, on-hand quantity, receipts | Inventory Ledger | `state/world/inventory.json` |
| Historical units sold per date | POS Sales History | `state/world/sales.json` |
| Demand-day label per date | Calendar/Holiday Service | `state/world/calendar.json` |
| Offers, prices, availability, lead times, order IDs, order lifecycle | each supplier | `state/world/supplier_SUPPLIER_A.json`, `..._B.json` |
| Raw record of every supplier call | the mock suppliers | `state/world/raw_calls/*.jsonl` |
| Store, destination, enabled SKUs, mappings, multipliers, limits | owner configuration | `fixtures/config.example.json` |
| Runs, per-SKU decisions, purchase attempts, reconciliation history, observed order IDs | this application | `state/app.sqlite3` |

The application **reads** the external world and **writes** only its own
SQLite database — plus the one consequential effect below, which changes
supplier state through the supplier's own API.

Application journal rows record what this application observed and attempted.
They never override contradictory authoritative external state. In particular,
`recorded_supplier_orders` stores an `observed_status`, not an authority.

## The consequential supplier operation

The only mutation this application performs on any external system is
`place_order`, declared on the supplier interface in
[`src/replenishment/interfaces.py`](src/replenishment/interfaces.py):

```python
def place_order(
    self,
    supplier_sku: str,          # the approved supplier SKU mapped to the store SKU
    quantity: int,              # positive, EACH, an exact multiple of the offer pack size
    expected_unit_price: Decimal,  # USD, two decimals; a compare-and-place condition
    destination_id: str,        # the single configured store destination
    idempotency_key: str,       # replenishment/<run_id>/<store_sku>/<supplier_id>
) -> PlaceOrderResult:          # OrderAccepted(order) | OrderRejected(code, message)
```

The local implementation is
`LocalSupplierService.place_order` in
[`src/replenishment/adapters/supplier.py`](src/replenishment/adapters/supplier.py).
It is reached from exactly one place in the application:

```
ReplenishmentEngine._execute            (src/replenishment/engine.py)
  -> Journal.commit_attempt             durable DISPATCHING record, committed first
  -> execution.place_purchase_order     (src/replenishment/execution.py)
       -> SupplierService.place_order   the one effectful call, made exactly once
```

An actual call recorded by the mock world looks like this:

```json
{
  "supplier_id": "SUPPLIER_B",
  "at": "2026-09-03T09:05:00.000000Z",
  "method": "place_order",
  "arguments": {
    "supplier_sku": "B-CHIPS-BBQ-150",
    "quantity": 84,
    "expected_unit_price": "0.78",
    "destination_id": "DEST-URBAN-01-DOCK",
    "idempotency_key": "replenishment/RUN-000001/SKU-CHIPS-BBQ-150G/SUPPLIER_B"
  },
  "outcome": "ACCEPTED",
  "detail": "supplier_order_id=B-PO-0009"
}
```

Everything else the application calls is a read: `get_snapshot`,
`get_receipts`, `get_daily_sales`, `get_days`, `get_offer`,
`get_order_snapshot`, and `lookup_by_idempotency_key`.

## How a run works

1. Take the process lock and refuse to start if another run is `RUNNING`.
2. Reconcile every unresolved purchase attempt by idempotency key, before any
   planning input is read and before any order is placed.
3. Obtain the Inventory Ledger snapshot. If it cannot be obtained, is stale,
   is from the future, or belongs to another store, the run fails and no
   purchase call is made.
4. Obtain each supplier's complete order snapshot and the matching ledger
   receipts.
5. For each configured SKU in ascending SKU order: check for a blocking
   unresolved attempt, read the ledger record, compute outstanding quantity,
   test the hard maximum, forecast from the 28-day window, build one candidate
   per usable offer, rank them, and place at most one order.
6. Finish as `COMPLETED`, `COMPLETED_WITH_EXCEPTIONS`, or `FAILED`.

## Configuration

See [`fixtures/config.example.json`](fixtures/config.example.json). JSON and
TOML are both accepted. The whole file is rejected before the scheduler starts
if a required field is missing, an unknown field is present, an identifier is
duplicated, a numeric range is invalid, money has more than two decimals, the
calendar labels are incomplete, a supplier mapping is ambiguous, or an adapter
cannot be constructed. Configuration is reloaded only on process restart; the
running application never edits it.

Relative `database_path` and `world_dir` values resolve against the directory
containing the configuration file.

## Layout

```
base-app/
  pyproject.toml
  README.md
  IMPLEMENTATION-NOTES.md
  fixtures/
    config.example.json          the committed example owner configuration
    world/                       the committed example external world
  src/replenishment/
    app.py            configuration + adapters + database + engine
    cli.py            the replenish command
    config.py         owner configuration loading and strict validation
    decimals.py       decimal parsing, money formatting, ceiling
    domain.py         the value types shared with the adapters
    engine.py         run orchestration and per-SKU decisions
    errors.py         the exception types
    execution.py      the durable attempt and the one place_order call
    forecast.py       28-day normalization and exponential smoothing
    interfaces.py     the external service boundaries
    journal.py        the durable journal
    locking.py        the single-worker process lock
    outstanding.py    outstanding quantity from orders and receipts
    planning.py       coverage horizon, target, pack rounding, exposure
    reconciliation.py resolution of unknown outcomes by idempotency key
    reporting.py      JSON and text operator reports
    scheduler.py      the daily scheduler
    selection.py      candidate feasibility, owner limits, and ranking
    storage.py        the SQLite schema
    timeutil.py       RFC 3339 and business-date helpers
    adapters/         local deterministic external services
  tests/
```

## Version-1 boundaries

No multiple stores or transfers, no fresh goods or expiry, no promotions
beyond calendar labels, no partial receipts or shipments, no order editing or
cancellation, no split orders or substitutions, no invoices or payment, no
supplier discovery, no automatic receiving, no concurrent workers, and no
probabilistic, machine-learned, or LLM-driven decisions.
