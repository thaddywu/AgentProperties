"""Rebuild reviewed reference artifacts without model calls."""
from pathlib import Path
from policyscope.adapters.reference import build

if __name__ == "__main__":
    build(Path(__file__).resolve().parents[1])
