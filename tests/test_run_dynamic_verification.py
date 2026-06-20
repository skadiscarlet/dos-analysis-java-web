import subprocess
from pathlib import Path

import pytest

from scripts.run_dynamic_verification import (
    CASES,
    OOM_EXIT_CODE,
    build_java_command,
    parse_summary,
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


def test_selected_cases_accepts_legacy_webdav_phase4_alias():
    from scripts.run_dynamic_verification import selected_cases

    selected = selected_cases(["WEB-P4-0025-0027"])

    assert [case.case_id for case in selected] == ["WEB-REAL-0006"]


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
