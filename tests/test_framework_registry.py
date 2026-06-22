import ast
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _phase2_databases() -> dict[str, str]:
    module = ast.parse((ROOT / "scripts/run_phase2.py").read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "DATABASES":
                    return {
                        key.value: ast.unparse(value)
                        for key, value in zip(node.value.keys, node.value.values)
                        if isinstance(key, ast.Constant)
                    }
    raise AssertionError("DATABASES not found in scripts/run_phase2.py")


def test_expansion_frameworks_are_registered_consistently():
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    frameworks = config["frameworks"]
    phase2_databases = _phase2_databases()
    build_script = (ROOT / "scripts/build_databases.sh").read_text(encoding="utf-8")

    expected = {
        "spring-boot-3": {
            "branch": "v3.5.15",
            "source_dir": "frameworks/spring-boot-3.5.15",
            "database": "databases/spring-boot-3-db",
            "build_helper": "scripts/codeql_build_spring_boot_3.sh",
        },
        "vertx": {
            "branch": "4.5.28",
            "source_dir": "frameworks/vertx-4.5.28-build-sources",
            "database": "databases/vertx-4-db",
            "build_helper": "scripts/codeql_build_vertx_4.sh",
        },
        "micronaut": {
            "branch": "v3.10.8",
            "source_dir": "frameworks/micronaut-core-3.10.8",
            "database": "databases/micronaut-3-db",
            "build_helper": "scripts/codeql_build_micronaut_3.sh",
        },
    }

    for framework, expected_meta in expected.items():
        assert frameworks[framework]["branch"] == expected_meta["branch"]
        assert frameworks[framework]["source_dir"] == expected_meta["source_dir"]
        assert frameworks[framework]["database"] == expected_meta["database"]
        assert framework in phase2_databases
        assert expected_meta["database"] in phase2_databases[framework]
        assert f"{framework})" in build_script
        assert expected_meta["build_helper"] in build_script
        assert (ROOT / expected_meta["build_helper"]).exists()

    assert frameworks["vertx"]["companion_repos"]["vertx-core"]["source_dir"] == "frameworks/vert.x-4.5.28"
    assert frameworks["vertx"]["companion_repos"]["vertx-web"]["source_dir"] == "frameworks/vertx-web-4.5.28"


def _extract_shell_function(script: str, name: str) -> str:
    start = script.index(f"{name}() {{")
    next_start = script.find("\nbuild_", start + 1)
    if next_start == -1:
        next_start = script.find("\n# 处理命令行参数", start)
    return script[start:next_start]


def test_expansion_database_builds_use_compilation_commands():
    build_script = (ROOT / "scripts/build_databases.sh").read_text(encoding="utf-8")

    for function_name in ("build_spring_boot_3", "build_vertx", "build_micronaut"):
        function_body = _extract_shell_function(build_script, function_name)
        assert "--command=" in function_body
        assert "--build-mode=none" not in function_body
        assert "buildless" not in function_body.lower()


def test_gradle_build_helpers_use_local_cache_and_long_wrapper_timeout():
    helpers = [
        ROOT / "scripts/codeql_build_spring_boot_3.sh",
        ROOT / "scripts/codeql_build_micronaut_3.sh",
    ]

    for helper in helpers:
        body = helper.read_text(encoding="utf-8")
        assert ".build-cache/gradle" in body
        assert "/home/furina/.gradle/wrapper/dists" in body
        assert "/home/furina/.gradle/caches/modules-2" in body
        assert "networkTimeout=120000" in body


def test_spring_boot_3_build_helper_compiles_stable_core_module_only():
    body = (ROOT / "scripts/codeql_build_spring_boot_3.sh").read_text(encoding="utf-8")

    assert ":spring-boot-project:spring-boot:clean" in body
    assert ":spring-boot-project:spring-boot:compileJava" in body
    assert "--no-build-cache" in body
    assert ":spring-boot-project:spring-boot-autoconfigure:compileJava" not in body
    assert ":spring-boot-project:spring-boot-actuator:compileJava" not in body


def test_vertx_build_helper_uses_local_maven_repo_with_central_fallback():
    body = (ROOT / "scripts/codeql_build_vertx_4.sh").read_text(encoding="utf-8")

    assert ".build-cache/m2/repository" in body
    assert "repo.maven.apache.org/maven2" in body
    assert "maven.aliyun.com/repository/public" in body
    assert "-DremoteRepositories=" in body


def test_vertx_database_uses_focused_source_view_not_whole_frameworks_dir():
    build_script = (ROOT / "scripts/build_databases.sh").read_text(encoding="utf-8")
    function_body = _extract_shell_function(build_script, "build_vertx")

    assert "vertx-4.5.28-build-sources" in function_body
    assert '--source-root="$FRAMEWORKS_DIR"' not in function_body
    assert "--exclude 'target/'" in function_body
    assert "--exclude '.git/'" in function_body


def test_micronaut_build_helper_uses_available_gradle_all_distribution():
    body = (ROOT / "scripts/codeql_build_micronaut_3.sh").read_text(encoding="utf-8")

    assert "gradle-7.5.1-all.zip" in body
    assert "gradle-7\\.5\\.1-bin\\.zip" in body
    assert "maven.aliyun.com/repository/gradle-plugin" in body
    assert "maven.aliyun.com/repository/public" in body
    assert "allprojects" in body
