import subprocess
from pathlib import Path

import pytest

from scripts.run_dynamic_verification import (
    CASES,
    STATIC_HUNT_CASES,
    OOM_EXIT_CODE,
    build_java_command,
    parse_summary,
    output_paths_for,
    selected_cases,
)


def test_cases_cover_web_real_and_webdav_targets():
    case_ids = {case.case_id for case in CASES}

    assert {
        "WEB-REAL-0001",
        "WEB-REAL-0002",
        "WEB-REAL-0003",
        "WEB-REAL-0004",
        "WEB-REAL-0005",
        "WEB-REAL-0006",
    }.issubset(case_ids)


def test_build_java_command_uses_real_http_probe_class_and_heap_limit():
    case = next(case for case in CASES if case.case_id == "WEB-REAL-0006")

    command = build_java_command(
        case,
        classpath="target/classes:/tmp/deps.jar",
        heap="384m",
        port_base=28100,
        run_profile="smoke",
    )

    assert command[:3] == ["java", "-Xmx384m", "-cp"]
    assert "target/classes:/tmp/deps.jar" in command
    assert "org.example.dos.dynamic.TomcatWebdavLocksHttpProbe" in command
    assert "28100" in command
    assert "smoke" in command


def test_static_hunt_tomcat_dead_properties_command_shape():
    case = next(case for case in STATIC_HUNT_CASES if case.case_id == "TOMCAT-STATIC-0003")

    command = build_java_command(
        case,
        classpath="target/classes:/tmp/deps.jar",
        heap=None,
        port_base=28200,
        run_profile="smoke",
    )

    assert command[:3] == ["java", "-Xmx384m", "-cp"]
    assert "org.example.dos.dynamic.TomcatWebdavDeadPropertiesHttpProbe" in command
    assert command[-6:] == ["64", "16", "512", "16", "28200", "smoke"]


def test_static_hunt_jetty_push_session_command_shape():
    case = next(case for case in STATIC_HUNT_CASES if case.case_id == "JETTY-STATIC-0002")

    command = build_java_command(case, "target/classes:/tmp/deps.jar", None, 28300, "smoke")

    assert "org.example.dos.dynamic.JettyPushSessionCacheHttpProbe" in command
    assert command[-5:] == ["128", "1024", "32", "28300", "smoke"]


def test_static_hunt_jetty_push_cache_command_shape():
    case = next(case for case in STATIC_HUNT_CASES if case.case_id == "JETTY-STATIC-0004")

    command = build_java_command(case, "target/classes:/tmp/deps.jar", None, 28310, "smoke")

    assert "org.example.dos.dynamic.JettyPushCacheFilterHttpProbe" in command
    assert command[-5:] == ["128", "1024", "32", "28310", "smoke"]


def test_static_hunt_undertow_multipart_command_shape():
    case = next(case for case in STATIC_HUNT_CASES if case.case_id == "UNDERTOW-STATIC-0003")

    command = build_java_command(case, "target/classes:/tmp/deps.jar", "384m", 28400, "smoke")

    assert command[:3] == ["java", "-Xmx384m", "-cp"]
    assert "org.example.dos.dynamic.UndertowMultipartHttpProbe" in command
    assert command[-5:] == ["32", "4096", "16", "28400", "smoke"]


def test_selected_cases_accepts_legacy_webdav_phase4_alias():
    selected = selected_cases(["WEB-P4-0025-0027"])

    assert [case.case_id for case in selected] == ["WEB-REAL-0006"]


def test_static_hunt_cases_cover_first_batch_without_web_real_ids():
    case_ids = {case.case_id for case in STATIC_HUNT_CASES}

    assert case_ids == {
        "TOMCAT-STATIC-0003",
        "JETTY-STATIC-0002",
        "JETTY-STATIC-0004",
        "UNDERTOW-STATIC-0003",
    }
    assert all(not case_id.startswith("WEB-REAL-") for case_id in case_ids)


def test_output_paths_separate_static_hunt_from_web_real_results():
    log_dir, summary_path = output_paths_for("static-hunt")

    assert log_dir.as_posix().endswith("results/static_hunts/dynamic_verification/logs")
    assert summary_path.as_posix().endswith(
        "results/static_hunts/dynamic_verification/static_hunt_dynamic_verification_summary.json"
    )


def test_selected_cases_can_target_static_hunt_registry():
    selected = selected_cases(["JETTY-STATIC-0002"], suite="static-hunt")

    assert [case.case_id for case in selected] == ["JETTY-STATIC-0002"]


def test_parse_summary_accepts_oom_exit_code_and_verdict(tmp_path):
    log = tmp_path / "probe.log"
    log.write_text(
        "\n".join(
            [
                "candidate=tomcat-webdav-locks-real-http",
                "maxHeapBytes=402653184",
                "verdict=CONFIRMED_HEAP_OOM_REAL_HTTP",
                "requestsBeforeOom=37",
                "resourceLocksBeforeOom=37",
            ]
        ),
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(["java"], OOM_EXIT_CODE)

    summary = parse_summary(completed, log)

    assert summary["status"] == "verified"
    assert summary["verdict"] == "CONFIRMED_HEAP_OOM_REAL_HTTP"
    assert summary["requestsBeforeOom"] == "37"


def test_parse_static_hunt_summary_normalizes_candidate_fields(tmp_path):
    from scripts.run_dynamic_verification import parse_static_hunt_summary

    log = tmp_path / "probe.log"
    log.write_text(
        "\n".join(
            [
                "candidate=tomcat-webdav-dead-properties-real-http",
                "verdict=CONFIRMED_HEAP_OOM_REAL_HTTP",
                "requestsBeforeOom=19",
                "deadPropertyPathsBeforeOom=19",
                "oomSignal=uncaught_handler",
            ]
        ),
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(["java"], OOM_EXIT_CODE)

    summary = parse_static_hunt_summary("TOMCAT-STATIC-0003", completed, log, require_oom=True)

    assert summary["candidate_id"] == "TOMCAT-STATIC-0003"
    assert summary["status"] == "verified"
    assert summary["verdict"] == "CONFIRMED_HEAP_OOM_REAL_HTTP"
    assert summary["oomSignal"] == "uncaught_handler"
    assert summary["requestsSent"] == "19"
    assert summary["retainedMetric"] == "deadPropertyPathsBeforeOom=19"
    assert summary["heap"] != ""
    assert summary["log"].endswith("probe.log")
    assert "notes" in summary


def test_parse_static_hunt_summary_records_non_oom_verdict_without_promotion(tmp_path):
    from scripts.run_dynamic_verification import parse_static_hunt_summary

    log = tmp_path / "probe.log"
    log.write_text(
        "\n".join(
            [
                "candidate=undertow-multipart-real-http",
                "verdict=NOT_VERIFIED_CLEANUP_BOUNDED",
                "requestsCompleted=512",
                "materializedParts=524288",
                "multipartFiles=524288",
                "cleanupRemovedTempFiles=true",
            ]
        ),
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(["java"], 0)

    summary = parse_static_hunt_summary("UNDERTOW-STATIC-0003", completed, log, require_oom=True)

    assert summary["candidate_id"] == "UNDERTOW-STATIC-0003"
    assert summary["status"] == "not_verified"
    assert summary["verdict"] == "NOT_VERIFIED_CLEANUP_BOUNDED"
    assert summary["requestsSent"] == "512"
    assert summary["retainedMetric"] == "multipartFiles=524288"
    assert "cleanupRemovedTempFiles=true" in summary["notes"]


def test_parse_summary_accepts_completed_smoke_run(tmp_path):
    log = tmp_path / "probe.log"
    log.write_text(
        "\n".join(
            [
                "candidate=tomcat-webdav-locks-real-http",
                "verdict=COMPLETED",
                "requestsCompleted=64",
                "resourceLocks=129",
            ]
        ),
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(["java"], 0)

    summary = parse_summary(completed, log, require_oom=False)

    assert summary["status"] == "completed_without_oom"
    assert summary["resourceLocks"] == "129"


def test_parse_summary_accepts_server_thread_heap_oom_without_verdict(tmp_path):
    log = tmp_path / "probe.log"
    log.write_text(
        "\n".join(
            [
                "candidate=jersey-multipart-real-http",
                "maxHeapBytes=402653184",
                "java.lang.OutOfMemoryError: Java heap space",
                "\tat org.jvnet.mimepull.MIMEParser.createBuf(MIMEParser.java:272)",
                'Exception in thread "main" java.io.IOException: Error writing request body to server',
            ]
        ),
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(["java"], 1)

    summary = parse_summary(completed, log)

    assert summary["status"] == "verified"
    assert summary["verdict"] == "CONFIRMED_HEAP_OOM_REAL_HTTP"
    assert summary["oomSignal"] == "server_thread_log"
    assert summary["processExitCode"] == "1"


def test_parse_summary_rejects_non_oom_failure(tmp_path):
    log = tmp_path / "probe.log"
    log.write_text("verdict=FAILED_WITH_NON_OOM\n", encoding="utf-8")
    completed = subprocess.CompletedProcess(["java"], 2)

    with pytest.raises(RuntimeError, match="did not confirm OOM"):
        parse_summary(completed, log)
