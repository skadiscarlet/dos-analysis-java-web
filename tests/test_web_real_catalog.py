import json
from pathlib import Path

from scripts.run_dynamic_verification import CASES


ROOT = Path(__file__).resolve().parents[1]


def test_webdav_tomcat_is_registered_as_web_real_0006():
    manifest = json.loads((ROOT / "intel/regression/web_real_manifest.json").read_text(encoding="utf-8"))
    case_ids = {case["id"] for case in manifest["cases"]}
    dynamic_case_ids = {case.case_id for case in CASES}

    assert "WEB-REAL-0006" in case_ids
    assert "WEB-REAL-0006" in dynamic_case_ids

    webdav = next(case for case in manifest["cases"] if case["id"] == "WEB-REAL-0006")
    assert webdav["framework"] == "servlet"
    assert webdav["component"] == "tomcat WebdavServlet"
    assert webdav["phase4_ids"] == ["WEB-P4-0025", "WEB-P4-0026", "WEB-P4-0027"]
