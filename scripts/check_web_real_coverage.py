#!/usr/bin/env python3
"""Compatibility wrapper for WEB-REAL static coverage checks."""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = BASE_DIR / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from check_web_real_regression import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
