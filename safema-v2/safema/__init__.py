"""SafeMA v1 research-prototype runtime."""

from .errors import ModelError, SafeMADenied, SafeMAError
from .runtime import SafeMARuntime, install


def register_resource(*args, **kwargs):
    """One-shot trusted control-plane registration without importing it at startup."""
    from .control_plane import TrustedControlPlane

    metadata_db = kwargs.pop("metadata_db")
    with TrustedControlPlane(metadata_db) as control_plane:
        return control_plane.register_resource(*args, **kwargs)


__all__ = [
    "ModelError",
    "SafeMADenied",
    "SafeMAError",
    "SafeMARuntime",
    "install",
    "register_resource",
]
