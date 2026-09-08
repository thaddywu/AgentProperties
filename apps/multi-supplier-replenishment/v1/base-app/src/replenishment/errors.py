"""Exception types used across the application."""

from __future__ import annotations


class ReplenishmentError(Exception):
    """Base class for every error raised by this application."""


class ConfigError(ReplenishmentError):
    """The owner configuration is missing, incomplete, or invalid."""


class RunLockError(ReplenishmentError):
    """Another replenishment run is already executing."""


class FatalRunError(ReplenishmentError):
    """A run-level failure that forbids any purchase call in the run."""


class ExternalServiceError(ReplenishmentError):
    """Base class for failures reported by an external service adapter."""


class ServiceUnavailable(ExternalServiceError):
    """The external service could not be reached or refused to answer."""


class MalformedResponse(ExternalServiceError):
    """The external service answered with data this application cannot use."""


class SupplierTimeout(ExternalServiceError):
    """A supplier call timed out; the external outcome is unknown."""


class SupplierTransportError(ExternalServiceError):
    """A supplier response was lost in transit; the external outcome is unknown."""
