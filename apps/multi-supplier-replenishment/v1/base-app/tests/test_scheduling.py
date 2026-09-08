"""Section 11 and policy Section 17: time-zone scheduling, daily catch-up,
manual runs, single-worker exclusion, and restart idempotency."""

from __future__ import annotations

from datetime import date

import pytest

from replenishment.domain import DecisionOutcome, RunStatus, TriggerKind
from replenishment.errors import RunLockError
from replenishment.journal import DuplicateScheduledRun
from replenishment.locking import RunLock
from replenishment.scheduler import Scheduler

from . import support
from .conftest import Scenario


@pytest.fixture
def daily(scenario: Scenario) -> Scenario:
    scenario.world.write_calendar()
    scenario.world.write_sales(
        {
            "SKU-1": {
                day.isoformat(): 10
                for day in support.date_span(date(2026, 7, 1), date(2026, 10, 31))
            }
        }
    )
    scenario.world.write_inventory({"SKU-1": 1000})
    scenario.world.write_supplier("SUPPLIER_A", offers={"A-1": support.offer()})
    scenario.world.write_supplier("SUPPLIER_B")
    scenario.configure([support.sku_config("SKU-1", mappings={"SUPPLIER_A": "A-1"})])
    return scenario


class RecordingSleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


# -- time zone and business dates -----------------------------------------


def test_the_business_date_comes_from_the_store_time_zone(daily: Scenario):
    # 03:30 UTC on 4 September is 23:30 on 3 September in New York.
    daily.set_instant("2026-09-04T03:30:00Z")
    outcome = daily.run()
    assert outcome.run.business_date == date(2026, 9, 3)
    assert outcome.results[0].detail["forecast"]["window_start"] == "2026-08-06"
    assert outcome.results[0].detail["forecast"]["window_end"] == "2026-09-02"


def test_the_scheduler_is_not_due_before_the_local_run_time(daily: Scenario):
    daily.set_instant("2026-09-03T08:30:00Z")  # 04:30 local
    with daily.open() as app:
        scheduler = Scheduler(app, sleeper=RecordingSleeper())
        status = scheduler.status()
        assert status.local_business_date == date(2026, 9, 3)
        assert status.due_now is False
        assert scheduler.tick() is None
        assert app.journal.list_runs() == []


def test_the_scheduler_runs_once_when_the_local_time_is_reached(daily: Scenario):
    daily.set_instant("2026-09-03T09:00:00Z")  # exactly 05:00 local
    with daily.open() as app:
        scheduler = Scheduler(app, sleeper=RecordingSleeper())
        assert scheduler.status().due_now is True
        outcome = scheduler.tick()
        assert outcome is not None
        assert outcome.run.trigger_kind is TriggerKind.SCHEDULED
        assert outcome.run.run_id == "RUN-000001"
        # A second tick in the same local day does nothing.
        assert scheduler.tick() is None
        assert len(app.journal.list_runs()) == 1


def test_startup_after_the_run_time_catches_up_once(daily: Scenario):
    daily.set_instant("2026-09-03T20:00:00Z")  # 16:00 local, long after 05:00
    sleeper = RecordingSleeper()
    with daily.open() as app:
        outcomes = Scheduler(app, sleeper=sleeper).serve(max_cycles=3)
    assert [outcome.run.run_id for outcome in outcomes] == ["RUN-000001"]
    assert sleeper.calls == [30.0, 30.0]


def test_a_completed_scheduled_run_is_not_repeated_across_a_restart(daily: Scenario):
    daily.set_instant("2026-09-03T09:05:00Z")
    with daily.open() as app:
        first = Scheduler(app, sleeper=RecordingSleeper()).tick()
    assert first is not None
    # The process restarts; the scheduler must not repeat the completed run.
    with daily.open() as app:
        assert Scheduler(app, sleeper=RecordingSleeper()).tick() is None
        runs = app.journal.list_runs()
        assert len(runs) == 1
        assert runs[0].status is RunStatus.COMPLETED
    # The supplier saw no second placement either.
    assert daily.world.raw_calls("SUPPLIER_A", method="place_order") == []


def test_a_scheduled_run_with_exceptions_is_also_not_repeated(scenario: Scenario):
    scenario.world.write_calendar()
    scenario.world.write_sales({"SKU-1": support.flat_sales(10)})
    scenario.world.write_inventory({"SKU-1": 0})
    scenario.world.write_supplier("SUPPLIER_A")  # no offer at all
    scenario.world.write_supplier("SUPPLIER_B")
    scenario.configure([support.sku_config("SKU-1", mappings={"SUPPLIER_A": "A-1"})])
    with scenario.open() as app:
        outcome = Scheduler(app, sleeper=RecordingSleeper()).tick()
        assert outcome.run.status is RunStatus.COMPLETED_WITH_EXCEPTIONS
    with scenario.open() as app:
        assert Scheduler(app, sleeper=RecordingSleeper()).tick() is None


def test_a_failed_scheduled_run_is_not_retried_automatically(scenario: Scenario):
    scenario.world.write_calendar()
    scenario.world.write_sales({"SKU-1": support.flat_sales(10)})
    scenario.world.write_inventory({"SKU-1": 0}, failure="unavailable")
    scenario.world.write_supplier("SUPPLIER_A", offers={"A-1": support.offer()})
    scenario.world.write_supplier("SUPPLIER_B")
    scenario.configure([support.sku_config("SKU-1", mappings={"SUPPLIER_A": "A-1"})])
    with scenario.open() as app:
        outcome = Scheduler(app, sleeper=RecordingSleeper()).tick()
        assert outcome.run.status is RunStatus.FAILED
    # The ledger recovers, but the scheduler still does not repeat the date.
    scenario.world.write_inventory({"SKU-1": 0})
    with scenario.open() as app:
        assert Scheduler(app, sleeper=RecordingSleeper()).tick() is None
        assert len(app.journal.list_runs()) == 1


def test_the_next_local_day_gets_its_own_scheduled_run(daily: Scenario):
    daily.set_instant("2026-09-03T09:05:00Z")
    with daily.open() as app:
        Scheduler(app, sleeper=RecordingSleeper()).tick()
    daily.set_instant("2026-09-04T09:05:00Z")
    with daily.open() as app:
        outcome = Scheduler(app, sleeper=RecordingSleeper()).tick()
        assert outcome is not None
        assert outcome.run.run_id == "RUN-000002"
        assert outcome.run.business_date == date(2026, 9, 4)


def test_a_second_scheduled_run_for_the_same_date_is_refused(daily: Scenario):
    with daily.open() as app:
        app.engine.execute(TriggerKind.SCHEDULED)
        with pytest.raises(DuplicateScheduledRun):
            app.engine.execute(TriggerKind.SCHEDULED)


# -- manual runs -----------------------------------------------------------


def test_a_manual_run_uses_the_same_logic_and_a_distinct_identity(daily: Scenario):
    with daily.open() as app:
        scheduled = app.engine.execute(TriggerKind.SCHEDULED)
        manual = app.engine.execute(TriggerKind.MANUAL)
    assert scheduled.run.run_id != manual.run.run_id
    assert manual.run.trigger_kind is TriggerKind.MANUAL
    assert manual.run.business_date == scheduled.run.business_date
    assert [item.outcome for item in manual.results] == [
        item.outcome for item in scheduled.results
    ]


def test_several_manual_runs_are_permitted_on_one_date(daily: Scenario):
    with daily.open() as app:
        first = app.engine.execute(TriggerKind.MANUAL)
        second = app.engine.execute(TriggerKind.MANUAL)
    assert [first.run.run_id, second.run.run_id] == ["RUN-000001", "RUN-000002"]


# -- single-worker exclusion ----------------------------------------------


def test_a_lock_held_by_another_worker_rejects_the_run(daily: Scenario):
    with daily.open() as app:
        other = RunLock(str(app.config.database_path) + ".lock")
        other.acquire()
        try:
            with pytest.raises(RunLockError, match="another replenishment worker"):
                app.engine.execute(TriggerKind.MANUAL)
        finally:
            other.release()
        assert app.journal.list_runs() == []


def test_a_durable_running_run_rejects_a_new_run(daily: Scenario):
    with daily.open(recover=False) as app:
        app.journal.create_run(
            TriggerKind.MANUAL, date(2026, 9, 3), app.services.clock.now()
        )
        with pytest.raises(RunLockError, match="RUNNING"):
            app.engine.execute(TriggerKind.MANUAL)


def test_an_interrupted_running_run_is_marked_failed_at_startup(daily: Scenario):
    with daily.open(recover=False) as app:
        run = app.journal.create_run(
            TriggerKind.MANUAL, date(2026, 9, 3), app.services.clock.now()
        )
    with daily.open() as app:
        assert app.journal.get_run(run.run_id).status is RunStatus.FAILED
        assert "interrupted" in app.journal.get_run(run.run_id).note
        # A new run may now start.
        outcome = app.engine.execute(TriggerKind.MANUAL)
        assert outcome.run.status is RunStatus.COMPLETED


def test_recovery_is_skipped_while_another_worker_holds_the_lock(daily: Scenario):
    with daily.open(recover=False) as app:
        run = app.journal.create_run(
            TriggerKind.MANUAL, date(2026, 9, 3), app.services.clock.now()
        )
        lock_path = str(app.config.database_path) + ".lock"
    other = RunLock(lock_path)
    other.acquire()
    try:
        with daily.open() as app:
            assert app.recovered == {"runs": [], "attempts": []}
            assert app.journal.get_run(run.run_id).status is RunStatus.RUNNING
    finally:
        other.release()


# -- restart idempotency ---------------------------------------------------


def test_restarting_never_duplicates_an_accepted_order(scenario: Scenario):
    scenario.world.write_calendar()
    scenario.world.write_sales({"SKU-1": support.flat_sales(10)})
    scenario.world.write_inventory({"SKU-1": 0})
    scenario.world.write_supplier(
        "SUPPLIER_A", offers={"A-1": support.offer(unit_price="1.00", pack_size=10)}
    )
    scenario.world.write_supplier("SUPPLIER_B")
    scenario.configure([support.sku_config("SKU-1", mappings={"SUPPLIER_A": "A-1"})])

    with scenario.open() as app:
        outcome = Scheduler(app, sleeper=RecordingSleeper()).tick()
        assert outcome.results[0].outcome is DecisionOutcome.ORDER_ACCEPTED

    for _ in range(3):
        with scenario.open() as app:
            assert Scheduler(app, sleeper=RecordingSleeper()).tick() is None

    assert len(scenario.world.raw_calls("SUPPLIER_A", method="place_order")) == 1
    assert len(scenario.world.supplier_orders("SUPPLIER_A")) == 1
