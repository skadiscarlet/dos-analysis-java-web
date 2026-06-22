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


def test_every_web_real_case_records_exploitability():
    manifest = json.loads((ROOT / "intel/regression/web_real_manifest.json").read_text(encoding="utf-8"))

    assert len(manifest["cases"]) == 12
    for case in manifest["cases"]:
        exploitability = case.get("exploitability")
        assert isinstance(exploitability, dict), case["id"]
        assert exploitability["difficulty"] in {"low", "medium", "high", "very_high"}
        assert isinstance(exploitability["default_exploitable"], bool), case["id"]
        assert exploitability["preconditions"], case["id"]
        assert exploitability["limiting_factors"], case["id"]
        assert exploitability["rationale"], case["id"]


def test_new_static_hunt_web_real_cases_are_marked_context_constrained():
    manifest = json.loads((ROOT / "intel/regression/web_real_manifest.json").read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in manifest["cases"]}

    assert cases["WEB-REAL-0007"]["source_static_id"] == "TOMCAT-STATIC-0003"
    assert cases["WEB-REAL-0007"]["phase3_regression"] == "dynamic_only_pending_query"
    assert cases["WEB-REAL-0007"]["exploitability"]["difficulty"] == "very_high"
    assert cases["WEB-REAL-0007"]["exploitability"]["default_exploitable"] is False
    assert "readonly=false" in " ".join(cases["WEB-REAL-0007"]["exploitability"]["preconditions"])

    assert cases["WEB-REAL-0008"]["source_static_id"] == "JETTY-STATIC-0002"
    assert cases["WEB-REAL-0008"]["phase3_regression"] == "dynamic_only_pending_query"
    assert cases["WEB-REAL-0008"]["exploitability"]["difficulty"] == "high"
    assert cases["WEB-REAL-0008"]["exploitability"]["default_exploitable"] is False

    assert cases["WEB-REAL-0009"]["source_static_id"] == "JETTY-STATIC-0004"
    assert cases["WEB-REAL-0009"]["phase3_regression"] == "dynamic_only_pending_query"
    assert cases["WEB-REAL-0009"]["exploitability"]["difficulty"] == "high"
    assert cases["WEB-REAL-0009"]["exploitability"]["default_exploitable"] is False


def test_new_framework_static_hunt_true_positives_are_web_real_context_cases():
    manifest = json.loads((ROOT / "intel/regression/web_real_manifest.json").read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in manifest["cases"]}

    assert cases["WEB-REAL-0010"]["source_static_id"] == "SB3-STATIC-0002"
    assert cases["WEB-REAL-0010"]["phase3_regression"] == "dynamic_only_pending_query"
    assert cases["WEB-REAL-0010"]["framework"] == "spring-boot"
    assert cases["WEB-REAL-0010"]["exploitability"]["difficulty"] == "medium"
    assert cases["WEB-REAL-0010"]["exploitability"]["default_exploitable"] is False
    assert "outbound" in " ".join(cases["WEB-REAL-0010"]["exploitability"]["preconditions"])

    assert cases["WEB-REAL-0011"]["source_static_id"] == "MN-STATIC-0002"
    assert cases["WEB-REAL-0011"]["phase3_regression"] == "dynamic_only_pending_query"
    assert cases["WEB-REAL-0011"]["framework"] == "micronaut"
    assert cases["WEB-REAL-0011"]["exploitability"]["difficulty"] == "medium"
    assert cases["WEB-REAL-0011"]["exploitability"]["default_exploitable"] is False
    assert "max-active-sessions" in " ".join(cases["WEB-REAL-0011"]["exploitability"]["preconditions"])

    assert cases["WEB-REAL-0012"]["source_static_id"] == "VERTX-STATIC-0003"
    assert cases["WEB-REAL-0012"]["phase3_regression"] == "dynamic_only_pending_query"
    assert cases["WEB-REAL-0012"]["framework"] == "vertx"
    assert cases["WEB-REAL-0012"]["exploitability"]["difficulty"] == "high"
    assert cases["WEB-REAL-0012"]["exploitability"]["default_exploitable"] is False
    assert "CachingWebClient" in " ".join(cases["WEB-REAL-0012"]["exploitability"]["preconditions"])


def test_new_framework_verified_vulnerabilities_have_oom_artifacts():
    catalog = json.loads((ROOT / "results/phase4/verified_vulnerabilities.json").read_text(encoding="utf-8"))
    vulnerabilities = {item["id"]: item for item in catalog["vulnerabilities"]}

    for case_id in ("WEB-REAL-0010", "WEB-REAL-0011", "WEB-REAL-0012"):
        verification = vulnerabilities[case_id]["real_http_verification"]
        assert verification["verdict"] == "CONFIRMED_HEAP_OOM_REAL_HTTP"
        assert (ROOT / verification["poc"]).exists()
        assert (ROOT / verification["log"]).exists()
        assert verification["log"].endswith("-oom.log")
