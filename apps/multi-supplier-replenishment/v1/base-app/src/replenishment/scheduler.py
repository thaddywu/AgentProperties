"""The long-running daily scheduler.

At most one scheduled run may complete for a local business date.  A failed or
interrupted scheduled run is never retried automatically; the operator inspects
it and may start a manual run.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

from .app import Application
from .domain import RunStatus, TriggerKind
from .engine import RunOutcome
from .errors import RunLockError
from .journal import DuplicateScheduledRun


@dataclass(frozen=True)
class SchedulerStatus:
    local_now: datetime
    local_business_date: date
    daily_run_time: str
    next_due_at: datetime
    due_now: bool
    scheduled_run_id: str | None
    scheduled_run_status: RunStatus | None

    def as_dict(self) -> dict[str, object]:
        return {
            "local_now": self.local_now.isoformat(),
            "local_business_date": self.local_business_date.isoformat(),
            "daily_run_time": self.daily_run_time,
            "next_due_at": self.next_due_at.isoformat(),
            "due_now": self.due_now,
            "todays_scheduled_run_id": self.scheduled_run_id,
            "todays_scheduled_run_status": (
                self.scheduled_run_status.value if self.scheduled_run_status else None
            ),
        }


class Scheduler:
    def __init__(
        self,
        application: Application,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.app = application
        self._sleep = sleeper

    def status(self) -> SchedulerStatus:
        config = self.app.config
        local_now = self.app.services.clock.now().astimezone(config.tzinfo)
        today = local_now.date()
        due_at = datetime.combine(today, config.daily_run_time, tzinfo=config.tzinfo)
        run = self.app.journal.scheduled_run_for(today)
        next_due = due_at if local_now < due_at else due_at + timedelta(days=1)
        if run is None and local_now >= due_at:
            next_due = due_at
        return SchedulerStatus(
            local_now=local_now,
            local_business_date=today,
            daily_run_time=config.daily_run_time.strftime("%H:%M"),
            next_due_at=next_due,
            due_now=run is None and local_now >= due_at,
            scheduled_run_id=run.run_id if run else None,
            scheduled_run_status=run.status if run else None,
        )

    def tick(self) -> RunOutcome | None:
        """Run once if today's scheduled run is due and has not been created."""
        status = self.status()
        if not status.due_now:
            return None
        try:
            return self.app.engine.execute(TriggerKind.SCHEDULED)
        except DuplicateScheduledRun:
            return None

    def serve(self, max_cycles: int | None = None) -> list[RunOutcome]:
        """Poll until stopped, executing the daily run when it becomes due."""
        outcomes: list[RunOutcome] = []
        cycles = 0
        poll_seconds = float(self.app.config.scheduler_poll_seconds)
        while max_cycles is None or cycles < max_cycles:
            cycles += 1
            try:
                outcome = self.tick()
            except RunLockError:
                outcome = None
            if outcome is not None:
                outcomes.append(outcome)
            if max_cycles is not None and cycles >= max_cycles:
                break
            self._sleep(poll_seconds)
        return outcomes
