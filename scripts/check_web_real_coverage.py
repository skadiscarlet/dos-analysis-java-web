#!/usr/bin/env python3
"""Check static Phase 3 coverage for dynamically verified WEB-REAL cases."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Callable

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = BASE_DIR / "results/phase3/phase3_candidate_features.csv"

Row = dict[str, str]
Matcher = Callable[[Row], bool]


def norm(value: str | None) -> str:
    return (value or "").strip()


def contains(row: Row, field: str, needle: str) -> bool:
    return needle in norm(row.get(field))


def equals(row: Row, field: str, expected: str) -> bool:
    return norm(row.get(field)) == expected


EXPECTATIONS: dict[str, Matcher] = {
    "WEB-REAL-0001": lambda row: (
        equals(row, "framework", "jersey")
        and equals(row, "candidate_family", "provider_state")
        and contains(row, "retained_field", "requestTokenByTokenString")
        and contains(row, "request_flow_kind", "provider_field")
    ),
    "WEB-REAL-0002": lambda row: (
        equals(row, "framework", "jersey")
        and equals(row, "candidate_family", "parser_body")
        and equals(row, "sink_shape", "parser_part_accumulator")
    ),
    "WEB-REAL-0003": lambda row: (
        equals(row, "framework", "undertow")
        and equals(row, "candidate_family", "listener_state")
        and equals(row, "request_flow_kind", "listener_callback")
        and contains(row, "retained_field", "cache")
    ),
    "WEB-REAL-0004": lambda row: (
        equals(row, "framework", "undertow")
        and equals(row, "candidate_family", "management_state")
        and equals(row, "request_flow_kind", "bounded_call_path")
        and norm(row.get("retained_field")) in {"nodes", "balancers"}
    ),
    "WEB-REAL-0005": lambda row: (
        equals(row, "framework", "jetty")
        and equals(row, "candidate_family", "client_destination")
        and equals(row, "request_flow_kind", "client_request_flow")
        and equals(row, "sink_shape", "retained_map_compute")
        and contains(row, "retained_field", "destinations")
    ),
}


def load_rows(path: Path) -> list[Row]:
    if not path.exists():
        raise FileNotFoundError(f"Phase 3 CSV not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Phase 3 merged CSV")
    args = parser.parse_args()

    rows = load_rows(args.input)
    missing: list[str] = []
    for vuln_id, matcher in EXPECTATIONS.items():
        hits = [row for row in rows if matcher(row)]
        if hits:
            sample = hits[0]
            print(
                f"{vuln_id}: hit "
                f"framework={norm(sample.get('framework'))} "
                f"candidate_family={norm(sample.get('candidate_family'))} "
                f"sink={norm(sample.get('sink_id'))}"
            )
        else:
            print(f"{vuln_id}: missing")
            missing.append(vuln_id)

    if missing:
        print("missing WEB-REAL coverage: " + ", ".join(missing), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
