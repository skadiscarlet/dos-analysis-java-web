import csv
import json

from scripts import check_web_real_regression


def test_dynamic_only_pending_query_cases_are_not_counted_as_missing(tmp_path):
    manifest = {
        "schema_version": 1,
        "cases": [
            {
                "id": "WEB-REAL-HIT",
                "framework": "demo",
                "component": "covered",
                "required": [{"field": "framework", "op": "equals", "value": "demo"}],
                "expected": [{"field": "sink_shape", "op": "equals", "value": "retained_map_put"}],
            },
            {
                "id": "WEB-REAL-DYNAMIC",
                "framework": "demo",
                "component": "dynamic only",
                "phase3_regression": "dynamic_only_pending_query",
                "required": [{"field": "framework", "op": "equals", "value": "absent"}],
                "expected": [],
            },
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    csv_path = tmp_path / "phase3.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["framework", "sink_shape"])
        writer.writeheader()
        writer.writerow({"framework": "demo", "sink_shape": "retained_map_put"})

    output_path = tmp_path / "report.json"

    assert check_web_real_regression.run(manifest_path, csv_path, output_path) == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert report["total_cases"] == 2
    assert report["hit"] == 1
    assert report["dynamic_only_pending_query"] == 1
    assert report["missing"] == 0
    dynamic_case = next(case for case in report["cases"] if case["id"] == "WEB-REAL-DYNAMIC")
    assert dynamic_case["status"] == "dynamic_only_pending_query"
