from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for location in (ROOT / "safema-v1", ROOT / "v1-impl"):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))
