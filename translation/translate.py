#!/usr/bin/env python3
"""Student entry point: original directory, enforced directory."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for directory in ('runtime/python', 'translation/python', 'query/python', 'evaluation'):
    sys.path.insert(0, str(ROOT / directory))

from policy_evaluation.porting.student import main

if __name__ == '__main__':
    main()
