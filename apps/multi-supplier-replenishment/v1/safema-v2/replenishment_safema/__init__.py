"""SafeMA v2 integration for the frozen replenishment Base App."""

from .integration import install_for_application
from .trusted_state import ReplenishmentTrustedStateResolver

__all__ = ["ReplenishmentTrustedStateResolver", "install_for_application"]
