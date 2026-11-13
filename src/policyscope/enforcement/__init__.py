"""Provider-neutral Python action runtime backed by Soufflé, plus a private worker client."""

from .client import (
    Applied,
    BridgeError,
    EffectNotAppliedError,
    NotApplied,
    ObservationSource,
    Operation,
    PolicyClient,
    Snapshot,
    Unknown,
)

__all__ = [
    "Applied",
    "BridgeError",
    "EffectNotAppliedError",
    "NotApplied",
    "ObservationSource",
    "Operation",
    "PolicyClient",
    "Snapshot",
    "Unknown",
]

from .runtime import AnalysisSnapshot, PolicyRuntime
from policyscope.core.policy import (
    compile_policy,
    fact,
    mechanism_predicates,
    policy_predicates,
)

__all__ += [
    "AnalysisSnapshot",
    "PolicyRuntime",
    "compile_policy",
    "fact",
    "mechanism_predicates",
    "policy_predicates",
]

from .api import DataRegistry, Policy
from .caller import caller_context, current_caller
from .transactions import sqlite_transaction

__all__ += [
    "DataRegistry",
    "Policy",
    "caller_context",
    "current_caller",
    "sqlite_transaction",
]

from .statements import StatementTool

__all__ += ["StatementTool"]

from .fact_tools import FactTool
from .recording import capture_trajectories

__all__ += ["FactTool"]
__all__ += ["capture_trajectories"]
