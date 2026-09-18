import subprocess
import tempfile
import unittest
from pathlib import Path

from dosweb.cli import main, parse_cli_values
from dosweb.config import DEFAULT_BASE_URL, DEFAULT_MODEL, load_config, resolve_api_key
from dosweb.errors import AnalyzerError


class ConfigTests(unittest.TestCase):
    def test_default_provider_uses_the_current_authorized_endpoint_and_model(self):
        result = load_config(
            cli_values={"database": Path("db"), "output": Path("out")},
            config_path=None,
            environ={},
        )
        self.assertEqual(result.llm.base_url, DEFAULT_BASE_URL)
        self.assertEqual(result.llm.model, DEFAULT_MODEL)
        self.assertEqual(DEFAULT_BASE_URL, "https://api.api2cn.com/v1/")
        self.assertEqual(DEFAULT_MODEL, "grok-4.6")

    def test_local_secrets_file_provides_the_api_key_without_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "local_secrets.json"
            secrets.write_text('{"deepseek_api_key": "sk-local-fixed-key"}', encoding="utf-8")
            secrets.chmod(0o600)
            result = load_config(
                cli_values={"database": Path("db"), "output": Path("out"), "allow_remote_llm": True},
                config_path=None,
                environ={},
                secrets_path=secrets,
            )
            self.assertEqual(result.llm.api_key, "sk-local-fixed-key")

    def test_environment_key_overrides_local_secrets_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "local_secrets.json"
            secrets.write_text('{"deepseek_api_key": "sk-local-fixed-key"}', encoding="utf-8")
            secrets.chmod(0o600)
            self.assertEqual(resolve_api_key({"DEEPSEEK_API_KEY": "sk-env-key"}, secrets), "sk-env-key")
            self.assertEqual(resolve_api_key({}, secrets), "sk-local-fixed-key")

    def test_local_secrets_file_rejects_group_or_world_readable_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "local_secrets.json"
            secrets.write_text('{"deepseek_api_key": "sk-local-fixed-key"}', encoding="utf-8")
            secrets.chmod(0o644)
            with self.assertRaises(AnalyzerError) as raised:
                resolve_api_key({}, secrets)
            self.assertEqual("CONFIG_SECRET_FILE_UNSAFE", raised.exception.code)

    def test_python_module_cli_runs_main_and_returns_invalid_argument_status(self):
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            ["python", "-m", "dosweb.cli", "unknown-command"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(
            completed.stderr,
            "CONFIG_INVALID_VALUE: Command-line arguments are invalid.\n",
        )

    def test_cli_returns_codeql_exit_three_for_formal_query_failure(self):
        class FailingPipeline:
            def run(self, _command: str) -> object:
                raise AnalyzerError("CODEQL_QUERY_FAILED", "selected query failed")
        self.assertEqual(
            main(["entries", "--database", "db", "--output", "out"], pipeline_factory=lambda _values: FailingPipeline()),
            3,
        )

    def test_cli_overrides_yaml_environment_and_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_text(
                "llm:\n"
                "  model: grok-4.6\n"
                "  base_url: https://yaml.example/\n"
                "  timeout_seconds: 41\n",
                encoding="utf-8",
            )
            result = load_config(
                cli_values={
                    "database": Path("db"),
                    "output": Path("out"),
                    "model": "grok-4.6",
                    "base_url": None,
                    "timeout_seconds": None,
                    "max_retries": None,
                    "temperature": None,
                    "codeql_binary": None,
                    "cache_dir": None,
                    "resume": False,
                },
                config_path=config,
                environ={
                    "DEEPSEEK_API_KEY": "test-secret",
                    "DEEPSEEK_BASE_URL": "https://env.example/",
                },
            )
        self.assertEqual(result.llm.model, "grok-4.6")
        self.assertEqual(result.llm.base_url, "https://yaml.example/")
        self.assertEqual(result.llm.timeout_seconds, 41)
        self.assertEqual(result.llm.api_key, "test-secret")

    def test_configuration_file_rejects_api_key_even_when_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_text("llm:\n  api_key: ''\n", encoding="utf-8")
            with self.assertRaises(AnalyzerError) as raised:
                load_config(
                    cli_values={"database": Path("db"), "output": Path("out")},
                    config_path=config,
                    environ={"DEEPSEEK_API_KEY": "test-secret"},
                )
        self.assertEqual(raised.exception.code, "CONFIG_SECRET_IN_FILE")
        self.assertEqual(raised.exception.exit_status, 2)

    def test_configuration_file_rejects_api_key_at_any_nested_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_text(
                "provider:\n  credentials:\n    api_key: forbidden\n",
                encoding="utf-8",
            )
            with self.assertRaises(AnalyzerError) as raised:
                load_config(
                    cli_values={"database": Path("db"), "output": Path("out")},
                    config_path=config,
                    environ={"DEEPSEEK_API_KEY": "test-secret"},
                )
        self.assertEqual(raised.exception.code, "CONFIG_SECRET_IN_FILE")

    def test_modeled_defaults_reject_sensitive_or_irrelevant_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_text(
                "analysis:\n  modeled_defaults:\n    spring.datasource.password: forbidden\n",
                encoding="utf-8",
            )
            with self.assertRaises(AnalyzerError) as raised:
                load_config(
                    cli_values={"database": Path("db"), "output": Path("out")},
                    config_path=config,
                    environ={},
                )
            self.assertEqual("CONFIG_INVALID_FILE", raised.exception.code)
        with self.assertRaises(AnalyzerError) as raised:
            load_config(
                cli_values={
                    "database": Path("db"), "output": Path("out"),
                    "modeled_default": ["service.api-key=forbidden"],
                },
                config_path=None,
                environ={},
            )
        self.assertEqual("CONFIG_INVALID_VALUE", raised.exception.code)

    def test_configuration_file_rejects_recursive_yaml_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_text("tree: &tree\n  child: *tree\n", encoding="utf-8")
            with self.assertRaises(AnalyzerError) as raised:
                load_config(
                    cli_values={"database": Path("db"), "output": Path("out")},
                    config_path=config,
                    environ={"DEEPSEEK_API_KEY": "test-secret"},
                )
        self.assertEqual(raised.exception.code, "CONFIG_INVALID_FILE")

    def test_configuration_file_rejects_excessive_nesting(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_text("nested: " * 129 + "value\n", encoding="utf-8")
            with self.assertRaises(AnalyzerError) as raised:
                load_config(
                    cli_values={"database": Path("db"), "output": Path("out")},
                    config_path=config,
                    environ={"DEEPSEEK_API_KEY": "test-secret"},
                )
        self.assertEqual(raised.exception.code, "CONFIG_INVALID_FILE")

    def test_configuration_file_wraps_invalid_utf8_with_safe_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_bytes(b"llm:\n  model: \xff\n")
            with self.assertRaises(AnalyzerError) as raised:
                load_config(
                    cli_values={"database": Path("db"), "output": Path("out")},
                    config_path=config,
                    environ={"DEEPSEEK_API_KEY": "test-secret"},
                )
        self.assertEqual(raised.exception.code, "CONFIG_INVALID_FILE")
        self.assertEqual(raised.exception.exit_status, 2)
        self.assertEqual(raised.exception.details["path"], str(config))

    def test_missing_environment_key_fails_when_remote_llm_is_explicitly_enabled(self):
        with self.assertRaises(AnalyzerError) as raised:
            load_config(
                cli_values={"database": Path("db"), "output": Path("out"), "allow_remote_llm": True},
                config_path=None,
                environ={},
            )
        self.assertEqual(
            raised.exception.code,
            "CONFIG_MISSING_DEEPSEEK_API_KEY",
        )

    def test_remote_llm_consent_and_source_paths_follow_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_text(
                "llm:\n"
                "  allow_remote_llm: false\n"
                "  public_source_url: https://github.com/yaml/repository\n"
                "  source_commit_sha: yaml-sha\n"
                "  source_checkout: yaml-checkout\n",
                encoding="utf-8",
            )
            result = load_config(
                cli_values={
                    "database": Path("db"),
                    "output": Path("out"),
                    "allow_remote_llm": True,
                    "public_source_url": "https://github.com/cli/repository/",
                    "source_commit_sha": "cli-sha",
                    "source_checkout": Path("checkout"),
                    "analysis_source_root": Path("analysis-checkout"),
                },
                config_path=config,
                environ={"DEEPSEEK_API_KEY": "test-secret"},
            )
        self.assertTrue(result.llm.allow_remote_llm)
        self.assertEqual(result.llm.public_source_url, "https://github.com/cli/repository")
        self.assertEqual(result.llm.source_commit_sha, "cli-sha")
        self.assertEqual(result.llm.source_checkout, Path("checkout"))
        self.assertEqual(result.llm.analysis_source_root, Path("analysis-checkout"))

    def test_analysis_source_root_defaults_to_source_checkout(self):
        result = load_config(
            cli_values={
                "database": Path("db"),
                "output": Path("out"),
                "source_checkout": Path("checkout"),
            },
            config_path=None,
            environ={},
        )
        self.assertEqual(result.llm.source_checkout, Path("checkout"))
        self.assertEqual(result.llm.analysis_source_root, Path("checkout"))

    def test_output_must_not_be_nested_in_analysis_source_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            with self.assertRaises(AnalyzerError) as raised:
                load_config(
                    cli_values={
                        "database": Path(tmp) / "database",
                        "output": source / "results/applications_static_analysis/run-1",
                        "source_checkout": source,
                        "analysis_source_root": source,
                    },
                    config_path=None,
                    environ={},
                )
        self.assertEqual(raised.exception.code, "CONFIG_OUTPUT_INSIDE_SOURCE")

    def test_llm_numeric_bounds_reject_zero_negative_nonfinite_and_excessive_temperature(self):
        for values in (
            {"timeout_seconds": 0}, {"max_retries": 0}, {"temperature": float("nan")},
            {"temperature": float("inf")}, {"temperature": -0.1}, {"temperature": 2.1},
        ):
            with self.subTest(values=values):
                with self.assertRaises(AnalyzerError) as raised:
                    load_config({"database": Path("db"), "output": Path("out"), **values}, None, {"DEEPSEEK_API_KEY": "test-key"})
                self.assertEqual(raised.exception.code, "CONFIG_INVALID_VALUE")

    def test_unknown_model_is_rejected_before_network_access(self):
        with self.assertRaises(AnalyzerError) as raised:
            load_config(
                cli_values={
                    "database": Path("db"),
                    "output": Path("out"),
                    "model": "deepseek-unknown",
                },
                config_path=None,
                environ={"DEEPSEEK_API_KEY": "test-secret"},
            )
        self.assertEqual(raised.exception.code, "CONFIG_UNSUPPORTED_MODEL")

    def test_disabled_remote_llm_allows_a_missing_environment_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_text("llm:\n  allow_remote_llm: false\n", encoding="utf-8")
            result = load_config(
                cli_values={"database": Path("db"), "output": Path("out")},
                config_path=config,
                environ={},
            )
        self.assertFalse(result.llm.allow_remote_llm)
        self.assertEqual(result.llm.api_key, "")

    def test_enabled_remote_llm_requires_a_nonblank_environment_key(self):
        with self.assertRaises(AnalyzerError) as raised:
            load_config(
                cli_values={"database": Path("db"), "output": Path("out"), "allow_remote_llm": True},
                config_path=None,
                environ={"DEEPSEEK_API_KEY": "  "},
            )
        self.assertEqual(raised.exception.code, "CONFIG_MISSING_DEEPSEEK_API_KEY")

    def test_configuration_rejects_api_key_spelling_variants_at_any_depth(self):
        for key in ("api-key", "apiKey", "API_KEY", "Api.Key"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                config = Path(tmp) / "config.yml"
                config.write_text(f"nested:\n  '{key}': forbidden\n", encoding="utf-8")
                with self.assertRaises(AnalyzerError) as raised:
                    load_config(
                        cli_values={"database": Path("db"), "output": Path("out")},
                        config_path=config,
                        environ={},
                    )
                self.assertEqual(raised.exception.code, "CONFIG_SECRET_IN_FILE")

    def test_yaml_input_is_byte_bounded_before_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_bytes(b"#" * (262144 + 1))
            with self.assertRaises(AnalyzerError) as raised:
                load_config({"database": Path("db"), "output": Path("out")}, config, {})
        self.assertEqual(raised.exception.code, "CONFIG_INVALID_FILE")

    def test_deep_yaml_is_controlled_even_when_parser_recurses(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
            with self.assertRaises(AnalyzerError) as raised:
                load_config({"database": Path("db"), "output": Path("out")}, config, {})
        self.assertEqual(raised.exception.code, "CONFIG_INVALID_FILE")

    def test_malformed_provider_base_urls_map_to_stable_config_error(self):
        for value in ("not-a-url", "https://localhost:invalid/", "https:///missing-host"):
            with self.subTest(value=value):
                with self.assertRaises(AnalyzerError) as raised:
                    load_config({"database": Path("db"), "output": Path("out"), "base_url": value}, None, {})
                self.assertEqual(raised.exception.code, "CONFIG_INVALID_VALUE")

    def test_config_rejects_unknown_root_and_llm_keys(self):
        for text in ("outpt: result\n", "llm:\n  provider: unsupported\n"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                config = Path(tmp) / "config.yml"
                config.write_text(text, encoding="utf-8")
                with self.assertRaises(AnalyzerError) as raised:
                    load_config({"database": Path("db"), "output": Path("out")}, config, {})
                self.assertEqual(raised.exception.code, "CONFIG_INVALID_FILE")

    def test_yaml_lone_surrogate_maps_to_invalid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_text('llm:\n  model: "\\uD800"\n', encoding="ascii")
            with self.assertRaises(AnalyzerError) as raised:
                load_config({"database": Path("db"), "output": Path("out")}, config, {})
        self.assertEqual(raised.exception.code, "CONFIG_INVALID_FILE")

    def test_cli_can_explicitly_revoke_yaml_remote_consent(self):
        values = parse_cli_values(["--database", "db", "--output", "out", "--no-remote-llm"])
        self.assertFalse(values["allow_remote_llm"])
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_text("llm:\n  allow_remote_llm: true\n", encoding="utf-8")
            loaded = load_config(values, config, {})
        self.assertFalse(loaded.llm.allow_remote_llm)

    def test_cli_exposes_remote_llm_consent_without_network(self):
        values = parse_cli_values([
            "--database", "db", "--output", "out", "--allow-remote-llm",
            "--public-source-url", "https://github.com/example/repo",
            "--source-commit-sha", "a" * 40, "--source-checkout", "checkout",
        ])
        self.assertTrue(values["allow_remote_llm"])
        self.assertEqual(values["database"], Path("db"))
        self.assertEqual(values["output"], Path("out"))

    def test_yaml_rejects_duplicates_alias_merge_tags_and_normalizes_paths(self):
        invalid_documents = (
            "llm:\n  api_key: forbidden\n  api_key: erased\n",
            "defaults: &defaults\n  timeout_seconds: 1\nllm:\n  <<: *defaults\n",
            "value: !!pairs [[a, b]]\n",
        )
        for document in invalid_documents:
            with self.subTest(document=document), tempfile.TemporaryDirectory() as tmp:
                config = Path(tmp) / "config.yml"
                config.write_text(document, encoding="utf-8")
                with self.assertRaises(AnalyzerError) as raised:
                    load_config({"database": Path("db"), "output": Path("out")}, config, {})
                self.assertIn(raised.exception.code, {"CONFIG_INVALID_FILE", "CONFIG_SECRET_IN_FILE"})

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_text("cache_dir: nested/cache\n", encoding="utf-8")
            loaded = load_config({"database": Path("db"), "output": Path("out")}, config, {})
        self.assertEqual(loaded.llm.cache_dir, Path("nested/cache"))

    def test_cli_boolean_flags_do_not_override_yaml_when_absent(self):
        values = parse_cli_values(["--database", "db", "--output", "out"])
        self.assertIsNone(values["allow_remote_llm"])
        self.assertIsNone(values["resume"])
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_text("llm:\n  allow_remote_llm: true\nresume: true\n", encoding="utf-8")
            loaded = load_config(values, config, {"DEEPSEEK_API_KEY": "test-key"})
        self.assertTrue(loaded.llm.allow_remote_llm)
        self.assertTrue(loaded.resume)

    def test_config_rejects_non_regular_and_malformed_authorities(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with self.assertRaises(AnalyzerError) as raised:
                load_config({"database": Path("db"), "output": Path("out")}, directory, {})
            self.assertEqual(raised.exception.code, "CONFIG_INVALID_FILE")
        for value in ("https://@api.deepseek.com/", "https://:@api.deepseek.com/", "https://api.deepseek.com:/", "https://[api.deepseek.com/"):
            with self.subTest(value=value), self.assertRaises(AnalyzerError) as raised:
                load_config({"database": Path("db"), "output": Path("out"), "base_url": value}, None, {})
            self.assertEqual(raised.exception.code, "CONFIG_INVALID_VALUE")

    def test_retry_and_timeout_have_explicit_upper_bounds_in_cli_and_yaml(self):
        from dosweb.config import MAX_LLM_RETRIES, MAX_LLM_TIMEOUT_SECONDS

        for cli_values, yaml_text in (
            ({"max_retries": MAX_LLM_RETRIES + 1}, None),
            ({}, f"llm:\n  max_retries: {MAX_LLM_RETRIES + 1}\n"),
            ({"timeout_seconds": MAX_LLM_TIMEOUT_SECONDS + 1}, None),
            ({}, f"llm:\n  timeout_seconds: {MAX_LLM_TIMEOUT_SECONDS + 1}\n"),
        ):
            with self.subTest(cli_values=cli_values, yaml_text=yaml_text), tempfile.TemporaryDirectory() as tmp:
                config = Path(tmp) / "config.yml"
                if yaml_text is not None:
                    config.write_text(yaml_text, encoding="utf-8")
                with self.assertRaises(AnalyzerError) as raised:
                    load_config(
                        {"database": Path("db"), "output": Path("out"), **cli_values},
                        config if yaml_text is not None else None,
                        {"DEEPSEEK_API_KEY": "test-key"},
                    )
                self.assertEqual(raised.exception.code, "CONFIG_INVALID_VALUE")
