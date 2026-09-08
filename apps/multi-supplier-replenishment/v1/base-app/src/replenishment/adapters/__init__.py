"""Local, deterministic implementations of every external service boundary.

These adapters contact no network and require no vendor account.  They keep
their own persistent state in a mock-world directory that is entirely separate
from the application's SQLite database.
"""
