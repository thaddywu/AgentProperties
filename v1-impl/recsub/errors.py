"""Exception types raised by the application core."""


class RecSubError(Exception):
    """Base class for every error raised by the application."""


class ConfigError(RecSubError):
    """Raised when configuration is missing, unreadable, or invalid."""


class ValidationError(RecSubError):
    """Raised when supplied data does not satisfy the specification."""


class NotFoundError(RecSubError):
    """Raised when a referenced record does not exist."""


class StateError(RecSubError):
    """Raised when an operation is not permitted in the record's current state."""


class PolicyViolation(RecSubError):
    """Raised when an external disclosure would violate the Safety Policy.

    The application never converts this into an external call: the guard in
    :mod:`recsub.policy` raises it *before* any gateway or agent is invoked.
    """
