"""Opt-in private evidence capture; it never grants execution authority."""

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import threading
import uuid

from policyscope.core.policy import fingerprint
from policyscope.core.contracts import (
    TRAJECTORY_FORMAT,
    TRAJECTORY_VERSION,
    TRAJECTORY_MAX_EVENTS,
)

_CAPTURE = ContextVar("policy_trajectory_capture", default=None)


@contextmanager
def capture_trajectories():
    """Collect recorders created by actual runtimes in this thread/task.

    Export each recorder after the application has finished. This is a trusted
    operator integration, never an agent tool or a replacement execution gate.
    """
    recordings = []
    token = _CAPTURE.set(recordings)
    try:
        yield recordings
    finally:
        _CAPTURE.reset(token)


class TrajectoryRecorder:
    def __init__(self, binding, source, policy_hash, inputs):
        self._header = dict(
            format=TRAJECTORY_FORMAT,
            version=TRAJECTORY_VERSION,
            traceId=uuid.uuid4().hex,
            policy=dict(binding=deepcopy(binding), source=source, hash=policy_hash),
            initialInputs=deepcopy(inputs),
            scope="Captured gate inputs and mediated callbacks. Outcomes follow the trusted adapter's confirmation contract; they are not independent proof of business success or authentic identity. Unmediated channels and missing observations remain outside this trace.",
        )
        self._events = []
        self._lock = threading.Lock()
        self._failed = False

    def ensure_capacity(self):
        if len(self._events) >= TRAJECTORY_MAX_EVENTS:
            raise ValueError(
                "Trajectory event limit reached; use a fresh recorded session."
            )

    def append(self, event):
        with self._lock:
            try:
                row = dict(deepcopy(event), sequence=len(self._events))
                row["hash"] = fingerprint(row)
                self._events.append(row)
            except Exception:
                self._failed = True
                raise

    def mark_failed(self):
        with self._lock:
            self._failed = True

    def export(self):
        with self._lock:
            if self._failed:
                raise ValueError(
                    "Recording is incomplete; it cannot certify a complete trajectory."
                )
            value = dict(deepcopy(self._header), events=deepcopy(self._events))
        return dict(value, id=fingerprint(value))


def create_recording(enabled, binding, source, policy_hash, inputs):
    collector = _CAPTURE.get()
    if not enabled and collector is None:
        return None
    recorder = TrajectoryRecorder(binding, source, policy_hash, inputs)
    if collector is not None:
        collector.append(recorder)
    return recorder
