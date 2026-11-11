"""Rebuild this app's reviewed reference metadata; no model is called."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1] / 'translation/tools'))
from build_reference import build

if __name__ == '__main__':
    build(ROOT)
