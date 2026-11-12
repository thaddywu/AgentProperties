#!/usr/bin/env python3
"""Run the optional Codex porting adapter from a checkout."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for directory in ('runtime/python', 'translation/python', 'query/python', 'evaluation'):
    sys.path.insert(0, str(ROOT / directory))

from policy_evaluation.porting.codex import main

if __name__ == '__main__':
    main()
