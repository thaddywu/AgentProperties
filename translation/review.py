#!/usr/bin/env python3
"""Open execution readings beside an explicitly selected original policy."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for directory in ('runtime/python', 'translation/python', 'query/python', 'evaluation'):
    sys.path.insert(0, str(ROOT / directory))

from policy_evaluation.__main__ import main

if __name__ == '__main__':
    main()
