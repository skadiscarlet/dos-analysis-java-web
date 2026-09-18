#!/usr/bin/env python3
"""Evaluate the PoC-33 21-library demo without modifying analyzer artifacts."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dosweb.benchmark.poc33_demo import main


if __name__ == "__main__":
    raise SystemExit(main())

