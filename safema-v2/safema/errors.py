"""SafeMA runtime exceptions."""


class SafeMAError(Exception):
    """Base class for SafeMA failures."""


class ModelError(SafeMAError):
    """A model cannot be loaded or an invocation cannot be interpreted."""


class OriginError(SafeMAError):
    """A trusted metadata origin returned unusable data."""


class SafeMADenied(SafeMAError):
    """Raised before a raw effect when the configured policy denies it."""

    def __init__(self, decision_id: int, reason: str) -> None:
        self.decision_id = decision_id
        self.reason = reason
        super().__init__(f"SAFEMA_DENIED[{decision_id}]: {reason}")
