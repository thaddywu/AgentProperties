"""Backend-owned observations and effects, shared by local and subprocess adapters."""

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

Context = dict[str, Any]
Fact = dict[str, Any]

TRAJECTORY_FORMAT = "policyscope-trajectory"
TRAJECTORY_VERSION = 1
TRAJECTORY_MAX_EVENTS = 1000


@dataclass(frozen=True)
class Applied:
    value: Any
    observations: list[Fact] = field(default_factory=list)
    status: str = field(default="applied", init=False)


@dataclass(frozen=True)
class NotApplied:
    reason: str
    status: str = field(default="not_applied", init=False)


@dataclass(frozen=True)
class Unknown:
    status: str = field(default="unknown", init=False)


@dataclass(frozen=True)
class Snapshot:
    version: str
    complete: bool
    facts: list[Fact]


@dataclass(frozen=True)
class ObservationSource:
    id: str
    predicates: Sequence[str]
    read: Callable[[Context], Snapshot]


@dataclass(frozen=True)
class Operation:
    action: str
    execute: Callable[[Context], Applied | NotApplied | Unknown]
    observations: Sequence[str] = ()
    # Backend-only rows captured from this operation's gate evaluation.
    reads: Sequence[str] = ()


class BridgeError(RuntimeError):
    def __init__(self, code: str, message: str, attempt_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.attempt_id = attempt_id


class EffectNotAppliedError(RuntimeError):
    """A trusted backend certifies all relevant effects were absent or rolled back."""
