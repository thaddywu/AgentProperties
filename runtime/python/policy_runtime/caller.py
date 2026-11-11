"""Application-supplied caller names, scoped to one dispatch; no authentication."""

from contextlib import contextmanager
from contextvars import ContextVar


_caller = ContextVar('policy_caller', default=None)


def current_caller():
    """Read the current caller name; never substitute the receiving service."""
    name = _caller.get()
    if name is None:
        raise RuntimeError('No caller name is available for this tool call.')
    return name


@contextmanager
def caller_context(name):
    """Carry an existing application caller name through a synchronous/async task."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError('Caller name must be a nonblank string.')
    token = _caller.set(name)
    try:
        yield
    finally:
        _caller.reset(token)
