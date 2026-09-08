from __future__ import annotations

import sys
from pathlib import Path

INTEGRATION_ROOT = Path(__file__).resolve().parents[1]
APP_VERSION_ROOT = INTEGRATION_ROOT.parent
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
for location in (REPOSITORY_ROOT / "safema-v1", APP_VERSION_ROOT / "base-app"):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))
