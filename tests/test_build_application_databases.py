import json
from pathlib import Path

import scripts.build_application_databases as builder
from scripts.build_application_databases import (
    ApplicationTarget,
    archive_urls_for_target,
    build_environment,
    build_command_for_target,
    build_plan_for_target,
    build_target,
    codeql_database_command,
    ensure_mirror_config,
    is_complete_source_tree,
    latest_status_records,
    load_manifest,
    rewrite_gradle_wrapper_distributions,
)


def target(**kwargs):
    defaults = {
        "id": "example__app",
        "full_name": "example/app",
        "clone_url": "https://github.com/example/app.git",
        "source_dir": "frameworks/applications/example__app",
        "database_dir": "databases/applications/example__app-db",
        "build_systems": ["maven"],
        "build_command": None,
    }
    defaults.update(kwargs)
    return ApplicationTarget(**defaults)


def test_load_manifest_uses_selected_targets_only(tmp_path):
    manifest = tmp_path / "targets.json"
    manifest.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "id": "a__app",
                        "full_name": "a/app",
                        "clone_url": "https://github.com/a/app.git",
                        "source_dir": "frameworks/applications/a__app",
                        "database_dir": "databases/applications/a__app-db",
                        "build_systems": ["maven"],
                    },
                    {
                        "id": "b__app",
                        "full_name": "b/app",
                        "clone_url": "https://github.com/b/app.git",
                        "source_dir": "frameworks/applications/b__app",
                        "database_dir": "databases/applications/b__app-db",
                        "build_systems": ["gradle"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    loaded = load_manifest(manifest, selected_ids={"b__app"})

    assert [item.id for item in loaded] == ["b__app"]


def test_maven_build_command_skips_tests_and_uses_local_repo(tmp_path):
    command = build_command_for_target(target(build_systems=["maven"]), tmp_path)

    assert command[0] == "mvn"
    assert "-s" in command
    assert str(tmp_path / ".build-cache/m2/settings-china.xml") in command
    assert f"-Dmaven.repo.local={tmp_path / '.build-cache/m2/repository'}" in command
    assert "-DskipTests" in command
    assert "-Dmaven.test.skip=true" in command
    assert "-Denforcer.skip=true" in command
    assert "-Dgpg.skip=true" in command
    assert "-Dfrontend.skip=true" in command
    assert "-Dskip.installnodenpm=true" in command
    assert "-Dskip.npm=true" in command
    assert "-Dskip.gulp=true" in command
    assert "-Dmaven.antrun.skip=true" in command
    assert command[-1] == "compile"


def test_gradle_build_command_uses_wrapper_when_present(tmp_path):
    source_dir = tmp_path / "frameworks/applications/example__app"
    source_dir.mkdir(parents=True)
    wrapper = source_dir / "gradlew"
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")

    command = build_command_for_target(
        target(source_dir="frameworks/applications/example__app", build_systems=["gradle"]),
        tmp_path,
    )

    assert command[:8] == [
        "./gradlew",
        "--no-daemon",
        "--max-workers=4",
        "-I",
        str(tmp_path / ".build-cache/gradle/init-china.gradle"),
        "-x",
        "test",
        "classes",
    ]
    assert command[-1] == "classes"


def test_custom_build_command_is_shell_wrapped_for_codeql(tmp_path):
    command = build_command_for_target(target(build_command="mvn -pl server compile"), tmp_path)

    assert command == ["bash", "-lc", "mvn -pl server compile"]


def test_auto_build_command_uses_nested_maven_root_when_repo_root_has_no_build_file(tmp_path):
    source_dir = tmp_path / "frameworks/applications/example__app"
    nested = source_dir / "server"
    nested.mkdir(parents=True)
    (nested / "pom.xml").write_text("<project />\n", encoding="utf-8")

    plan = build_plan_for_target(
        target(source_dir="frameworks/applications/example__app", build_systems=["auto"]),
        tmp_path,
    )

    assert plan.cwd == source_dir
    assert plan.build_root == nested
    assert plan.command[:3] == ["mvn", "-f", "server/pom.xml"]
    assert any(arg.startswith("-Dmaven.repo.local=") for arg in plan.command)


def test_auto_build_command_prefers_java17_springboot_backend_root(tmp_path):
    source_dir = tmp_path / "frameworks/applications/example__app"
    (source_dir / "web-ui").mkdir(parents=True)
    legacy = source_dir / "api-java8"
    preferred = source_dir / "api-java17-springboot3"
    legacy.mkdir()
    preferred.mkdir()
    (legacy / "pom.xml").write_text("<project />\n", encoding="utf-8")
    (preferred / "pom.xml").write_text("<project />\n", encoding="utf-8")

    plan = build_plan_for_target(
        target(source_dir="frameworks/applications/example__app", build_systems=["auto"]),
        tmp_path,
    )

    assert plan.cwd == source_dir
    assert plan.build_root == preferred
    assert plan.command[:3] == ["mvn", "-f", "api-java17-springboot3/pom.xml"]


def test_auto_build_command_checks_second_level_backend_roots(tmp_path):
    source_dir = tmp_path / "frameworks/applications/example__app"
    service = source_dir / "backend" / "resource-service"
    agent = source_dir / "agent"
    service.mkdir(parents=True)
    agent.mkdir()
    (service / "pom.xml").write_text("<project />\n", encoding="utf-8")
    (agent / "pom.xml").write_text("<project />\n", encoding="utf-8")

    plan = build_plan_for_target(
        target(source_dir="frameworks/applications/example__app", build_systems=["auto"]),
        tmp_path,
    )

    assert plan.cwd == source_dir
    assert plan.build_root == service
    assert plan.command[:3] == ["mvn", "-f", "backend/resource-service/pom.xml"]


def test_codeql_database_command_uses_build_mode_extraction_paths():
    command = codeql_database_command(
        target(),
        project_root=Path("/repo"),
        threads=4,
        ram_mb=4096,
        overwrite=True,
        build_command=["mvn", "compile"],
    )

    assert command[:6] == [
        "/usr/bin/codeql",
        "database",
        "create",
        "/repo/databases/applications/example__app-db",
        "--language=java",
        "--source-root=/repo/frameworks/applications/example__app",
    ]
    assert "--command=mvn compile" in command
    assert "--overwrite" in command


def test_incomplete_git_directory_is_not_treated_as_ready_source(tmp_path):
    source_dir = tmp_path / "frameworks/applications/example__app"
    (source_dir / ".git").mkdir(parents=True)

    assert not is_complete_source_tree(source_dir)

    (source_dir / "pom.xml").write_text("<project />\n", encoding="utf-8")

    assert is_complete_source_tree(source_dir)


def test_archive_source_tree_with_build_file_is_treated_as_ready_source(tmp_path):
    source_dir = tmp_path / "frameworks/applications/example__app"
    source_dir.mkdir(parents=True)
    (source_dir / "pom.xml").write_text("<project />\n", encoding="utf-8")

    assert is_complete_source_tree(source_dir)


def test_archive_urls_try_common_branches_and_accelerators():
    urls = archive_urls_for_target(target(full_name="Example/App"), ["https://gh-proxy.test/"])

    assert urls[0] == "https://codeload.github.com/Example/App/zip/refs/heads/main"
    assert urls[1] == "https://codeload.github.com/Example/App/zip/refs/heads/master"
    assert "https://gh-proxy.test/https://codeload.github.com/Example/App/zip/refs/heads/main" in urls


def test_clone_target_retries_without_partial_clone_after_failure(tmp_path, monkeypatch):
    app = target(source_dir="frameworks/applications/example__app")
    source_dir = tmp_path / app.source_dir
    calls = []

    def fake_run_command(command, cwd, log_path, timeout_seconds, env=None):
        calls.append(command)
        source_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / ".git").mkdir(exist_ok=True)
        if len(calls) == 1:
            (source_dir / "partial.tmp").write_text("bad checkout\n", encoding="utf-8")
            return "failed", 128, 1.0
        assert not (source_dir / "partial.tmp").exists()
        (source_dir / "pom.xml").write_text("<project />\n", encoding="utf-8")
        return "succeeded", 0, 2.0

    monkeypatch.setattr(builder, "run_command", fake_run_command)

    record = builder.clone_target(app, tmp_path, tmp_path / "results", timeout_seconds=30, attempts=2)

    assert record["status"] == "succeeded"
    assert record["attempts"] == 2
    assert "--filter=blob:none" in calls[0]
    assert "--filter=blob:none" not in calls[1]


def test_clone_target_tries_github_accelerator_after_direct_attempts_fail(tmp_path, monkeypatch):
    app = target(source_dir="frameworks/applications/example__app")
    source_dir = tmp_path / app.source_dir
    calls = []

    def fake_run_command(command, cwd, log_path, timeout_seconds, env=None):
        calls.append(command)
        source_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / ".git").mkdir(exist_ok=True)
        if len(calls) < 3:
            return "failed", 128, 1.0
        (source_dir / "pom.xml").write_text("<project />\n", encoding="utf-8")
        return "succeeded", 0, 2.0

    monkeypatch.setattr(builder, "run_command", fake_run_command)

    record = builder.clone_target(
        app,
        tmp_path,
        tmp_path / "results",
        timeout_seconds=30,
        attempts=2,
        accelerator_prefixes=["https://gh-proxy.test/"],
    )

    assert record["status"] == "succeeded"
    assert record["url_attempts"] == 2
    assert calls[0][-2] == "https://github.com/example/app.git"
    assert calls[2][-2] == "https://gh-proxy.test/https://github.com/example/app.git"


def test_download_archive_source_enforces_total_download_timeout(tmp_path, monkeypatch):
    class SlowResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, size=-1):
            return b"x"

    ticks = iter([0.0, 0.0, 2.0, 2.0])

    monkeypatch.setattr(builder, "urlopen", lambda url, timeout: SlowResponse())
    monkeypatch.setattr(builder.time, "monotonic", lambda: next(ticks))

    status, returncode, _seconds = builder.download_archive_source(
        "https://example.test/archive.zip",
        tmp_path / "source",
        timeout_seconds=1,
        log_path=tmp_path / "archive.log",
    )

    assert (status, returncode) == ("failed", 1)
    assert "archive download exceeded 1 seconds" in (tmp_path / "archive.log").read_text(encoding="utf-8")


def test_build_target_creates_database_parent_before_codeql_dry_run(tmp_path):
    source_dir = tmp_path / "frameworks/applications/example__app"
    source_dir.mkdir(parents=True)
    (source_dir / "pom.xml").write_text("<project />\n", encoding="utf-8")

    record = build_target(
        target(),
        project_root=tmp_path,
        results_dir=tmp_path / "results/application_dbs",
        threads=4,
        ram_mb=4096,
        overwrite=True,
        timeout_seconds=1,
        dry_run=True,
    )

    assert (tmp_path / "databases/applications").is_dir()
    assert record["status"] == "build_dry_run"


def test_build_target_retries_requested_java_homes_until_success(tmp_path, monkeypatch):
    source_dir = tmp_path / "frameworks/applications/example__app"
    source_dir.mkdir(parents=True)
    (source_dir / "pom.xml").write_text("<project />\n", encoding="utf-8")
    java_homes = []

    def fake_run_command(command, cwd, log_path, timeout_seconds, env=None):
        java_homes.append(env["JAVA_HOME"])
        return ("failed", 2, 1.0) if len(java_homes) == 1 else ("succeeded", 0, 2.0)

    monkeypatch.setattr(builder, "run_command", fake_run_command)

    record = build_target(
        target(),
        project_root=tmp_path,
        results_dir=tmp_path / "results/application_dbs",
        threads=4,
        ram_mb=4096,
        overwrite=True,
        timeout_seconds=1,
        dry_run=False,
        java_homes=["/jdk17", "/jdk22"],
    )

    assert record["status"] == "build_succeeded"
    assert record["java_home"] == "/jdk22"
    assert record["attempts"] == 2
    assert java_homes == ["/jdk17", "/jdk22"]


def test_ensure_mirror_config_writes_china_first_maven_and_gradle_files(tmp_path):
    config = ensure_mirror_config(tmp_path)

    maven_settings = config.maven_settings.read_text(encoding="utf-8")
    gradle_init = config.gradle_init.read_text(encoding="utf-8")

    assert "https://maven.aliyun.com/repository/public" in maven_settings
    assert "https://mirrors.tencent.com/nexus/repository/maven-public/" in maven_settings
    assert "https://repo.maven.apache.org/maven2" in maven_settings
    assert "https://maven.aliyun.com/repository/gradle-plugin" in gradle_init
    assert "gradlePluginPortal()" in gradle_init


def test_rewrite_gradle_wrapper_distributions_points_wrappers_at_china_mirror(tmp_path):
    wrapper = tmp_path / "gradle/wrapper/gradle-wrapper.properties"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text(
        "distributionUrl=https\\://services.gradle.org/distributions/gradle-9.5.0-bin.zip\n",
        encoding="utf-8",
    )

    rewritten = rewrite_gradle_wrapper_distributions(tmp_path, "https://mirrors.cloud.tencent.com/gradle/")

    assert rewritten == [wrapper]
    assert "https\\://mirrors.cloud.tencent.com/gradle/gradle-9.5.0-bin.zip" in wrapper.read_text(encoding="utf-8")


def test_latest_status_records_keeps_latest_record_per_target(tmp_path):
    status_path = tmp_path / "status.jsonl"
    status_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "target_id": "a__app",
                        "full_name": "a/app",
                        "phase": "clone",
                        "status": "failed",
                    }
                ),
                json.dumps(
                    {
                        "target_id": "a__app",
                        "full_name": "a/app",
                        "status": "build_succeeded",
                        "database_dir": "/repo/databases/a-db",
                    }
                ),
                json.dumps(
                    {
                        "target_id": "b__app",
                        "full_name": "b/app",
                        "phase": "clone",
                        "status": "timeout",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    records = latest_status_records(status_path)

    assert [(record["target_id"], record["status"]) for record in records] == [
        ("a__app", "build_succeeded"),
        ("b__app", "clone_timeout"),
    ]


def test_build_environment_uses_requested_java_home(tmp_path):
    env = build_environment(tmp_path, java_home="/usr/lib/jvm/java-21-openjdk")

    assert env["JAVA_HOME"] == "/usr/lib/jvm/java-21-openjdk"
    assert env["PATH"].startswith("/usr/lib/jvm/java-21-openjdk/bin:")
