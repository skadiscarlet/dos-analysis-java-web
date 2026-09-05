# Java Web DoS P0 Analyzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete, resumable P0 static analyzer for Spring MVC, Servlet, Netty, and MQTT that extracts lifecycle facts with CodeQL, validates bounded-slice Growth Contracts through DeepSeek, deterministically evaluates assertions 1 and 2, and emits auditable static findings and lifecycle certificates.

**Architecture:** A Python 3.11 package owns CLI orchestration, strict artifacts, provider access, deterministic verification, conclusions, and reports. CodeQL queries emit raw, replayable facts but never verdicts. DeepSeek is mandatory for a complete P0 run, yet its structured response can only become verified growth after deterministic mapping back to the bounded slice and extracted facts.

**Tech Stack:** Python 3.11+, standard-library `argparse`/`dataclasses`/`json`/`urllib`/`unittest`, PyYAML 6.x, CodeQL CLI and `codeql/java-all`, Java fixture sources, JSON/JSONL artifacts.

## Global Constraints

- Preserve `databases/`, `frameworks/`, `poc/`, `results/static_hunts/`, `results/application*`, `results/java_web_dos_batch/`, and the 2026-07-02 v2 baseline design.
- Do not restore the retired phase-oriented analyzer or legacy verdict compatibility.
- Ordinary scans produce only `static_vulnerable`, `bounded_under_modeled_assumptions`, or `static_unknown`.
- Never describe a static finding as dynamically confirmed.
- P0 does not launch services, send attack traffic, or run dynamic DoS validation.
- P0 covers baseline Spring MVC, Servlet, Netty, and MQTT patterns; relevant unsupported patterns force `static_unknown`.
- P0 implements assertions 1 and 2 only. Asynchronous Release capacity and assertion 3 are deferred.
- DeepSeek calls use an environment-only `DEEPSEEK_API_KEY`; configuration files containing `api_key` are rejected.
- A missing key or failed/invalid provider response fails a complete P0 run. A valid semantic `unknown` response is a successful provider call and a conservative analysis result.
- Default tests are network-free. Real CodeQL fixture tests and real DeepSeek tests are explicit opt-ins.
- Keep files focused by responsibility; do not combine query execution, LLM access, lifecycle reasoning, and reporting.
- Every project modification updates `CHANGELOG.md`.
- The approved design and this plan are ignored by the broad `docs/superpowers/` rule. Track them with `git add -f` only after explicit commit authorization.
- Commit steps in this plan are execution checkpoints; run them only after the user authorizes commits.

---

## File Map

### Runtime and packaging

- Create `pyproject.toml` — Python version, package metadata, PyYAML dependency, and console entry point.
- Create `dos-web-analyzer` — repository-local executable wrapper around `dosweb.cli:main`.
- Create `dosweb/__init__.py` — package version.
- Create `dosweb/cli.py` — command parsing, exit-code translation, and pipeline dispatch.
- Create `dosweb/config.py` — CLI/YAML/environment/default merging and secret rejection.
- Create `dosweb/errors.py` — stable error codes and exit statuses.
- Create `dosweb/pipeline.py` — stage orchestration and resume decisions.

### Artifacts

- Create `dosweb/artifacts/identifiers.py` — canonical JSON, SHA-256, stable IDs, file hashes.
- Create `dosweb/artifacts/schemas.py` — explicit record validators and reference checks.
- Create `dosweb/artifacts/jsonl.py` — strict JSON/JSONL reads and atomic publication.
- Create `dosweb/artifacts/metadata.py` — run/stage metadata, fingerprints, and invalidation.

### CodeQL bridge and queries

- Create `dosweb/codeql/database.py` — database validation and fingerprinting.
- Create `dosweb/codeql/runner.py` — query execution and BQRS decode subprocesses.
- Create `dosweb/codeql/decoder.py` — strict query-column contracts and raw fact normalization.
- Create `codeql/qlpack.yml` — P0 query pack.
- Create four files under `codeql/dosweb/Entries/` — framework entry facts.
- Create four files under `codeql/dosweb/Growth/` — G1–G4 candidates.
- Create `codeql/dosweb/Flows/EntryToGrowth.ql` — attacker-controlled flow facts.
- Create three files under `codeql/dosweb/Lifecycle/` — Guard, Bound, and synchronous Release candidates.

### Domain analysis

- Create `dosweb/entries/models.py` and `dosweb/entries/normalize.py` — entry records and stable IDs.
- Create `dosweb/growth/models.py`, `slices.py`, `contracts.py`, and `verify.py` — Growth candidates, slices, model contracts, and deterministic verification.
- Create `dosweb/flows/models.py` and `verify.py` — flow records and proof validation.
- Create `dosweb/lifecycle/guards.py`, `bounds.py`, `releases.py`, and `certificates.py` — lifecycle decisions and evidence certificates.
- Create `dosweb/conclude/assertions.py` and `verdicts.py` — assertion 1/2 evaluation and three-value conclusion.
- Create `dosweb/llm/client.py`, `deepseek.py`, `prompts.py`, `schemas.py`, and `cache.py` — provider protocol, DeepSeek adapter, strict prompt/response contract, and persistent cache.
- Create `dosweb/report/summary.py` and `markdown.py` — machine and human reports from the same normalized findings.

### Tests and fixtures

- Create focused `unittest` modules under `tests/` for artifacts, config/CLI, provider, decoder, entries, growth, flows, lifecycle, assertions, pipeline recovery, reports, and P0 E2E.
- Create self-contained Java fixtures under `tests/fixtures/{spring,servlet,netty,mqtt}/` with local framework stubs and no network dependency.
- Modify the existing static-infrastructure and dynamic-helper tests for the new verdict vocabulary.

### Active documentation and compatibility tools

- Modify `scripts/aggregate_java_web_dos_batch.py` — accept only the new verdict vocabulary.
- Modify `scripts/prepare_dynamic_validation_output.py` — preserve the new static verdict as traceability metadata without changing dynamic semantics.
- Modify `README.md` and `AGENTS.md` — document the P0 implementation, lifecycle limitations, and new verdict vocabulary.
- Modify `CHANGELOG.md` after each implementation task without overwriting the existing approved-design entry.

---

### Task 1: Establish the Package, Errors, Configuration, and Artifact Primitives

**Files:**
- Create: `pyproject.toml`
- Create: `dos-web-analyzer`
- Create: `dosweb/__init__.py`
- Create: `dosweb/errors.py`
- Create: `dosweb/config.py`
- Create: `dosweb/artifacts/__init__.py`
- Create: `dosweb/artifacts/identifiers.py`
- Create: `dosweb/artifacts/schemas.py`
- Create: `dosweb/artifacts/jsonl.py`
- Create: `dosweb/artifacts/metadata.py`
- Create: `tests/test_config_and_cli.py`
- Create: `tests/test_artifact_contracts.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: `AnalyzerError(code: str, message: str, details: Mapping[str, object] | None = None)` with `.exit_status`.
- Produces: `load_config(cli_values, config_path, environ) -> AnalyzerConfig`.
- Produces: `canonical_json(value) -> bytes`, `sha256_canonical_json(value) -> str`, `stable_identifier(prefix, semantic_identity) -> str`, and `file_sha256(path) -> str`.
- Produces: `read_jsonl_strict(path, artifact_name) -> list[dict[str, object]]` and `write_jsonl_atomically(path, artifact_name, records, known_ids) -> ArtifactRef`.
- Produces: `StageFingerprint`, `reusable_stage(run, stage_name, expected, output_root) -> bool`, and `invalidate_from(run, first_stage, ordered_stages) -> None` for Task 7.

- [ ] **Step 1: Write configuration and error tests**

Create `tests/test_config_and_cli.py` with tests that fix the public contract:

```python
import os
import tempfile
import unittest
from pathlib import Path

from dosweb.config import load_config
from dosweb.errors import AnalyzerError


class ConfigTests(unittest.TestCase):
    def test_cli_overrides_yaml_environment_and_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yml"
            config.write_text(
                "llm:\n"
                "  model: deepseek-v4-flash\n"
                "  base_url: https://yaml.example/\n"
                "  timeout_seconds: 41\n",
                encoding="utf-8",
            )
            result = load_config(
                cli_values={
                    "database": Path("db"),
                    "output": Path("out"),
                    "model": "deepseek-v4-pro",
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
        self.assertEqual(result.llm.model, "deepseek-v4-pro")
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

    def test_missing_environment_key_fails_complete_configuration(self):
        with self.assertRaises(AnalyzerError) as raised:
            load_config(
                cli_values={"database": Path("db"), "output": Path("out")},
                config_path=None,
                environ={},
            )
        self.assertEqual(
            raised.exception.code,
            "CONFIG_MISSING_DEEPSEEK_API_KEY",
        )

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
```

- [ ] **Step 2: Run the configuration tests and confirm the missing package failure**

Run:

```bash
python -m unittest tests.test_config_and_cli -v
```

Expected: `ERROR` with `ModuleNotFoundError: No module named 'dosweb'`.

- [ ] **Step 3: Implement packaging, errors, and configuration**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "dos-analysis-web"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["PyYAML>=6.0,<7"]

[project.scripts]
dos-web-analyzer = "dosweb.cli:main"

[tool.setuptools.packages.find]
include = ["dosweb*"]
```

Create `dosweb/errors.py` around this exact mapping:

```python
from collections.abc import Mapping
from typing import Any


_EXIT_STATUS_BY_PREFIX = {
    "CONFIG_": 2,
    "CODEQL_": 3,
    "LLM_": 4,
    "ARTIFACT_": 5,
    "ANALYSIS_": 6,
    "COVERAGE_": 6,
    "INTERNAL_": 6,
}


class AnalyzerError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})

    @property
    def exit_status(self) -> int:
        for prefix, status in _EXIT_STATUS_BY_PREFIX.items():
            if self.code.startswith(prefix):
                return status
        return 6
```

Create frozen `LlmConfig` and `AnalyzerConfig` dataclasses in `dosweb/config.py`. Use `yaml.safe_load`, reject a non-object root, reject any `llm.api_key` key, normalize the base URL to one trailing slash, accept only `deepseek-v4-pro` and `deepseek-v4-flash`, and implement this precedence:

```text
CLI value if not None
else YAML value if present
else environment value if supported
else default
```

Use defaults `https://api.deepseek.com/`, `deepseek-v4-pro`, timeout `60`, retries `3`, temperature `0`, CodeQL binary `codeql`, cache `<output>/cache/llm`, and `resume=False`. Read the key only from `DEEPSEEK_API_KEY`.

Create executable `dos-web-analyzer`:

```python
#!/usr/bin/env python3
from dosweb.cli import main

raise SystemExit(main())
```

For now, create `dosweb/cli.py` with `main()` that supports `--help` and returns `2` for an `AnalyzerError`; Task 7 will add stage orchestration.

- [ ] **Step 4: Run configuration tests and verify they pass**

Run:

```bash
python -m unittest tests.test_config_and_cli -v
```

Expected: all four tests `ok`.

- [ ] **Step 5: Write strict artifact tests**

Create `tests/test_artifact_contracts.py` covering canonical identity, invalid JSON constants, non-object rows, atomic publication, and stage invalidation:

```python
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dosweb.artifacts.identifiers import sha256_canonical_json, stable_identifier
from dosweb.artifacts.jsonl import read_jsonl_strict, write_jsonl_atomically
from dosweb.artifacts.metadata import StageFingerprint, invalidate_from, reusable_stage
from dosweb.errors import AnalyzerError


class ArtifactContractTests(unittest.TestCase):
    def test_hash_and_identifier_ignore_mapping_key_order(self):
        left = {"framework": "servlet", "handler": {"line": 10, "file": "A.java"}}
        right = {"handler": {"file": "A.java", "line": 10}, "framework": "servlet"}
        self.assertEqual(sha256_canonical_json(left), sha256_canonical_json(right))
        self.assertEqual(stable_identifier("entry", left), stable_identifier("entry", right))

    def test_reader_rejects_non_standard_json_with_path_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "facts.jsonl"
            path.write_text('{"value": NaN}\n', encoding="utf-8")
            with self.assertRaises(AnalyzerError) as raised:
                read_jsonl_strict(path, "entry_facts")
        self.assertEqual(raised.exception.code, "ARTIFACT_INVALID_JSON")
        self.assertEqual(raised.exception.details["line"], 1)

    def test_reader_rejects_non_object_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "facts.jsonl"
            path.write_text('[1, 2, 3]\n', encoding="utf-8")
            with self.assertRaises(AnalyzerError) as raised:
                read_jsonl_strict(path, "entry_facts")
        self.assertEqual(raised.exception.code, "ARTIFACT_RECORD_NOT_OBJECT")

    def test_atomic_writer_does_not_publish_when_validation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "entry_facts.jsonl"
            with self.assertRaises(AnalyzerError):
                write_jsonl_atomically(
                    path,
                    "entry_facts",
                    [{"entry_id": ""}],
                    known_ids={},
                )
            self.assertFalse(path.exists())

    def test_resume_rejects_changed_upstream_hash_and_invalidates_downstream(self):
        fingerprint = StageFingerprint(
            schema_version="2.0",
            tool_version="0.1.0",
            implementation_version="entries-v1",
            database_fingerprint="db-a",
            query_pack_hash="ql-a",
            config_hash="config-a",
            upstream_hashes={"input": "old"},
        )
        run = {
            "stages": {
                "entries": {"status": "completed", "fingerprint": fingerprint.to_dict()},
                "growth": {"status": "completed"},
                "flows": {"status": "completed"},
            }
        }
        changed = StageFingerprint(**{**fingerprint.__dict__, "upstream_hashes": {"input": "new"}})
        self.assertFalse(reusable_stage(run, "entries", changed, Path(".")))
        invalidate_from(run, "entries", ["entries", "growth", "flows"])
        self.assertEqual(run["stages"]["entries"]["status"], "invalid")
        self.assertEqual(run["stages"]["growth"]["status"], "invalid")
```

- [ ] **Step 6: Run artifact tests and confirm they fail on missing implementations**

Run:

```bash
python -m unittest tests.test_artifact_contracts -v
```

Expected: import errors for `dosweb.artifacts` modules.

- [ ] **Step 7: Implement artifact primitives minimally and atomically**

Implement these exact public signatures in `dosweb/artifacts/identifiers.py`: `canonical_json(value: object) -> bytes`, `sha256_canonical_json(value: object) -> str`, `stable_identifier(prefix: str, semantic_identity: Mapping[str, object]) -> str`, and `file_sha256(path: Path) -> str`.

Use sorted keys, compact separators, UTF-8, `allow_nan=False`, and IDs shaped as `<prefix>:<first-24-hex>`.

In `schemas.py`, define `SCHEMA_VERSION = "2.0"`, required-field validators for every artifact name from the approved design, enum checks, non-empty stable IDs, and `validate_references(artifact_name, records, known_ids) -> None`. Start with the entry schema needed by the tests, but include the complete artifact registry so later tasks extend validators rather than inventing new entry points.

In `jsonl.py`, parse with `parse_constant` that raises, attach path and line details, reject non-objects, write sorted canonical records to a same-directory temporary file, flush and `fsync`, re-read and validate, `os.replace`, and `fsync` the parent directory. Return:

```python
@dataclass(frozen=True)
class ArtifactRef:
    path: str
    sha256: str
    record_count: int
    schema_version: str
```

In `metadata.py`, define `StageFingerprint.to_dict()`, strict equality comparison in `reusable_stage`, output-artifact existence/hash checks, and ordered invalidation beginning at `first_stage`.

- [ ] **Step 8: Run the focused tests and full existing suite**

Run:

```bash
python -m unittest tests.test_config_and_cli tests.test_artifact_contracts -v
python -m unittest discover -s tests -v
```

Expected: focused tests pass; pre-existing tests remain green.

- [ ] **Step 9: Update the changelog and checkpoint**

Append a concise entry under the existing 2026-07-18 section for package/config/artifact foundations and the exact verification commands. Do not remove the approved-design text already present.

If commits are authorized:

```bash
git add pyproject.toml dos-web-analyzer dosweb tests/test_config_and_cli.py tests/test_artifact_contracts.py CHANGELOG.md
git commit -m "feat: add P0 configuration and artifact contracts"
```

Expected: one focused commit; otherwise leave a cleanly reviewable working-tree checkpoint.

---

### Task 2: Add the Audited DeepSeek Growth Contract Adapter

**Files:**
- Create: `dosweb/llm/__init__.py`
- Create: `dosweb/llm/client.py`
- Create: `dosweb/llm/schemas.py`
- Create: `dosweb/llm/prompts.py`
- Create: `dosweb/llm/cache.py`
- Create: `dosweb/llm/deepseek.py`
- Create: `dosweb/growth/__init__.py`
- Create: `dosweb/growth/models.py`
- Create: `dosweb/growth/contracts.py`
- Create: `tests/test_deepseek_client.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `LlmConfig`, `AnalyzerError`, canonical hashing, and atomic JSON publication from Task 1.
- Produces: `BoundedSlice`, `GrowthContract`, `DeepSeekClient.classify_growth(slice_) -> GrowthContract`, and `ContractCache` for Task 5.

- [ ] **Step 1: Write provider schema, retry, cache, and redaction tests**

Create a local `ThreadingHTTPServer` fixture in `tests/test_deepseek_client.py`. Its handler records request count, path, headers, and body, then returns scripted responses. Add test methods named:

- `test_valid_contract_uses_openai_compatible_chat_completions`
- `test_semantic_unknown_is_a_successful_contract`
- `test_429_and_500_are_retried_up_to_configured_attempts`
- `test_401_fails_without_retry`
- `test_empty_or_non_json_content_fails_schema_validation`
- `test_successful_cache_hit_skips_second_http_request`
- `test_failed_response_is_not_written_as_success_cache`
- `test_cache_and_error_text_do_not_contain_api_key_or_authorization`

Each method scripts the local handler response, invokes `DeepSeekClient.classify_growth`, and asserts the returned contract or exact `AnalyzerError.code`, request count, and cache state.

Use this valid content payload:

```python
VALID_CONTRACT = {
    "is_resource_growth": "yes",
    "growth_kind": "container_growth",
    "resource_dimension": "entries",
    "attacker_influence": [{"target": "key", "evidence_id": "fact:key"}],
    "resource_effect": "Adds one attacker-selected key to a persistent map.",
    "required_static_evidence": ["fact:key", "fact:put"],
    "confidence": "high",
}
```

Assert the request path is `/chat/completions`, the request model is `deepseek-v4-pro`, temperature is `0`, and the only secret-bearing location is the outbound `Authorization: Bearer ...` header observed by the local server.

- [ ] **Step 2: Run provider tests and verify imports fail**

Run:

```bash
python -m unittest tests.test_deepseek_client -v
```

Expected: import failure for `dosweb.llm.deepseek`.

- [ ] **Step 3: Define bounded-slice and contract dataclasses**

In `dosweb/growth/models.py`, define:

```python
@dataclass(frozen=True)
class BoundedSlice:
    slice_id: str
    entry_id: str
    growth_id: str
    normalized_payload: Mapping[str, object]
    static_evidence_ids: frozenset[str]
    allowed_locations: frozenset[tuple[str, int]]


@dataclass(frozen=True)
class GrowthContract:
    is_resource_growth: Literal["yes", "no", "unknown"]
    growth_kind: Literal[
        "input_materialization",
        "direct_allocation",
        "container_growth",
        "async_work_growth",
        "unknown",
    ]
    resource_dimension: Literal[
        "entries", "bytes", "tasks", "connections", "objects", "unknown"
    ]
    attacker_influence: tuple[Mapping[str, object], ...]
    resource_effect: str
    required_static_evidence: tuple[str, ...]
    confidence: Literal["high", "medium", "low"]
```

In `contracts.py`, implement `validate_growth_contract(payload)` with exact allowed keys and enums. Unknown or extra fields fail with `LLM_RESPONSE_SCHEMA_INVALID`; do not silently coerce strings, arrays, or numbers.

- [ ] **Step 4: Implement prompt and cache identity**

Set constants:

```python
PROMPT_VERSION = "growth-contract-v1"
RESPONSE_SCHEMA_VERSION = "growth-contract-schema-v1"
```

`build_growth_messages(slice_)` returns one system and one user message. The system message states that the model must use only supplied facts, return one JSON object without Markdown, and put unprovable claims in `required_static_evidence` or answer `unknown`.

Implement cache identity over provider, canonical base URL, model, temperature, timeout, prompt version, response schema version, and normalized slice. Persist successful entries atomically at `<cache_dir>/<sha256>.json`; include a redacted request audit, raw response, parsed contract, and hashes. Reject cache entries whose schema version, key, or hashes do not match.

- [ ] **Step 5: Implement the standard-library DeepSeek client**

Define a provider protocol in `client.py`:

```python
class GrowthClassifier(Protocol):
    def classify_growth(self, slice_: BoundedSlice) -> GrowthContract:
        raise NotImplementedError
```

In `deepseek.py`:

- Canonicalize the URL with `urljoin(base_url, "chat/completions")`.
- POST JSON with model, messages, and temperature.
- Parse `choices[0].message.content` as one strict JSON object.
- Retry only timeout, interrupted connection, HTTP 429, and HTTP 500–599.
- Fail immediately on 401/403, other 4xx, empty response, malformed envelope, invalid contract, or refusal without a valid contract.
- Use bounded exponential backoff; inject `sleep` and jitter functions so tests do not wait.
- Redact the configured key, `Authorization` values, and `sk-...` shaped strings from error details and audit output.
- Write cache only after strict response validation succeeds.

Map exhausted retry failures to `LLM_RETRIES_EXHAUSTED`, invalid contracts to `LLM_RESPONSE_SCHEMA_INVALID`, authentication to `LLM_AUTHENTICATION_FAILED`, and malformed envelopes to `LLM_RESPONSE_INVALID`.

- [ ] **Step 6: Run provider tests**

Run:

```bash
python -m unittest tests.test_deepseek_client -v
```

Expected: all provider tests pass without external network access.

- [ ] **Step 7: Add the opt-in online test without enabling it by default**

Create `tests/integration/test_deepseek_online.py` guarded by both `DOSWEB_RUN_DEEPSEEK_INTEGRATION=1` and `DEEPSEEK_API_KEY`. It must submit only an artificial fixture slice and assert the response validates as a `GrowthContract`. If either guard is absent, call `self.skipTest(...)`.

Do not run this test during normal implementation. Document this explicit command in the test module docstring:

```bash
DOSWEB_RUN_DEEPSEEK_INTEGRATION=1 DEEPSEEK_API_KEY=... \
python -m unittest tests.integration.test_deepseek_online -v
```

- [ ] **Step 8: Run the default suite and update the changelog**

Run:

```bash
python -m unittest tests.test_deepseek_client -v
python -m unittest discover -s tests -v
```

Expected: all default tests pass and no outbound DeepSeek request occurs.

If commits are authorized:

```bash
git add dosweb/llm dosweb/growth tests/test_deepseek_client.py tests/integration/test_deepseek_online.py CHANGELOG.md
git commit -m "feat: add audited DeepSeek growth contracts"
```

---

### Task 3: Add the Strict CodeQL Runner and Decoder Contracts

**Files:**
- Create: `dosweb/codeql/__init__.py`
- Create: `dosweb/codeql/database.py`
- Create: `dosweb/codeql/runner.py`
- Create: `dosweb/codeql/decoder.py`
- Create: `codeql/qlpack.yml`
- Create: `tests/test_codeql_adapter.py`
- Create: `tests/test_codeql_decoder.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: artifact hashing and `AnalyzerError` from Task 1.
- Produces: `validate_database(path) -> DatabaseInfo`, `run_query(...) -> QueryResult`, `decode_rows(query_name, columns, rows, source) -> list[dict]`, and fixed `QuerySpec` column contracts for Tasks 4–6.

- [ ] **Step 1: Write database, subprocess, and strict-column tests**

Create test methods named:

- `test_database_requires_metadata_and_java_database_directory`
- `test_database_fingerprint_changes_when_metadata_changes`
- `test_query_failure_reports_codeql_query_failed_without_secret_environment`
- `test_decoder_rejects_missing_extra_or_reordered_columns`
- `test_decoder_rejects_invalid_enums_and_non_integer_lines`
- `test_decoder_normalizes_paths_relative_to_database_source_root`

Each test constructs a temporary database or mocked subprocess result, invokes the exact public function, and asserts the returned dataclass or exact stable error code. The failure test also asserts that the exception details omit the complete environment and any `DEEPSEEK_API_KEY` value.

Use exact shared entry columns:

```python
ENTRY_COLUMNS = (
    "framework", "protocol", "handler_fqn", "handler_file",
    "handler_start_line", "registration_kind", "registration_fqn",
    "registration_file", "registration_start_line", "route_or_event",
    "auth_context", "attacker_input_name", "attacker_input_type",
    "attacker_input_kind", "materialization_phase", "coverage_status",
    "coverage_note",
)
```

Add fixed tuples for growth, flow, Guard, Bound, and Release using the approved design column contracts. Reordered columns must fail rather than be matched by name.

- [ ] **Step 2: Run tests and confirm missing-module failures**

Run:

```bash
python -m unittest tests.test_codeql_adapter tests.test_codeql_decoder -v
```

Expected: import failures.

- [ ] **Step 3: Implement database validation and query execution**

Define:

```python
@dataclass(frozen=True)
class DatabaseInfo:
    path: Path
    source_root: Path
    fingerprint: str

@dataclass(frozen=True)
class QueryResult:
    query_name: str
    query_path: Path
    bqrs_path: Path
    decoded_path: Path
    query_sha256: str
    bqrs_sha256: str
```

`validate_database` requires `codeql-database.yml` and `db-java/`. Fingerprint canonical metadata plus stable hashes of database metadata files, not the mutable output directory name.

`run_query` executes:

```text
codeql query run <query> --database <db> --output <temporary.bqrs>
codeql bqrs decode <temporary.bqrs> --format=json --output <temporary.json>
```

Pass a minimal environment inherited from the caller without logging it. Capture stdout/stderr, map failures to `CODEQL_QUERY_FAILED`, and publish BQRS/decoded outputs only after both commands succeed.

- [ ] **Step 4: Implement strict `QuerySpec` decoding**

Define one `QuerySpec` per query family. `decode_bqrs_json` must validate the expected result set, exact ordered columns, row arity, primitive types, paths, one-based line numbers, and enums. It returns raw fact dictionaries with `query_name`, `query_sha256`, and normalized source locations, but no verdict.

Never fill missing columns with `None`; never ignore extra columns; never derive an `entry_id` or `growth_id` from row order.

- [ ] **Step 5: Create the query pack manifest**

Create `codeql/qlpack.yml`:

```yaml
name: dosweb/p0-java-resource-dos
version: 0.1.0
libraryPathDependencies:
  codeql/java-all: "*"
```

Do not add query suites until individual queries exist in later tasks.

- [ ] **Step 6: Run adapter and decoder tests**

Run:

```bash
python -m unittest tests.test_codeql_adapter tests.test_codeql_decoder -v
```

Expected: all tests pass with mocked CodeQL subprocesses.

- [ ] **Step 7: Update changelog and checkpoint**

If commits are authorized:

```bash
git add dosweb/codeql codeql/qlpack.yml tests/test_codeql_adapter.py tests/test_codeql_decoder.py CHANGELOG.md
git commit -m "feat: add strict CodeQL execution contracts"
```

---

### Task 4: Extract Registered Entries for Spring MVC, Servlet, Netty, and MQTT

**Files:**
- Create: `dosweb/entries/__init__.py`
- Create: `dosweb/entries/models.py`
- Create: `dosweb/entries/normalize.py`
- Create: `codeql/dosweb/Entries/SpringMvcEntries.ql`
- Create: `codeql/dosweb/Entries/ServletEntries.ql`
- Create: `codeql/dosweb/Entries/NettyEntries.ql`
- Create: `codeql/dosweb/Entries/MqttEntries.ql`
- Create: `tests/test_entries.py`
- Create: `tests/test_codeql_entry_queries.py`
- Create: Java sources under `tests/fixtures/{spring,servlet,netty,mqtt}/src/main/java/`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `ENTRY_COLUMNS` and raw query facts from Task 3.
- Produces: `EntryFact.from_raw(raw) -> EntryFact`, `normalize_entry_rows(rows) -> list[dict]`, stable `entry_id`, and framework coverage records for Tasks 5–7.

- [ ] **Step 1: Write entry normalization tests before QL implementation**

Test that:

- identical semantic entries get the same ID regardless of row order;
- class and method Spring routes normalize to one route;
- a Servlet subclass without registration is not accepted as an entry;
- a Netty `channelRead` method requires an `initChannel -> addLast` registration fact;
- an MQTT listener implementation requires a static subscribe/callback registration fact;
- unknown auth remains `unknown`, not `unauthenticated`;
- dynamic/reflection registration emits a `partial` coverage record and `forces_unknown`.

Use this normalized semantic shape, with `entry_id` asserted using `stable_identifier("entry", semantic_identity)` rather than a literal hash:

```python
semantic_identity = {
    "framework": "spring_mvc",
    "protocol": "http",
    "handler": {
        "callable": "fixture.spring.SpringFixture.handle",
        "file": "fixture/spring/SpringFixture.java",
        "start_line": 10,
    },
    "registration": {
        "kind": "annotation_mapping",
        "callable": "fixture.spring.SpringFixture.handle",
        "file": "fixture/spring/SpringFixture.java",
        "start_line": 8,
    },
    "route_or_event": "/items",
    "auth_context": "unknown",
    "attacker_inputs": [
        {"name": "body", "type": "byte[]", "kind": "request_body"}
    ],
    "materialization_phase": "before_handler",
}
expected = {
    "entry_id": stable_identifier("entry", semantic_identity),
    **semantic_identity,
}
```

- [ ] **Step 2: Run entry tests and confirm failure**

Run:

```bash
python -m unittest tests.test_entries -v
```

Expected: missing `dosweb.entries` imports.

- [ ] **Step 3: Implement entry models and normalization**

Use frozen dataclasses for handler/registration/input facts and `EntryFact`. Derive `entry_id` only from framework, protocol, normalized handler location, normalized registration identity, route/event, and attacker input identity. Do not include timestamps, output paths, or query row indexes.

Merge duplicate rows for one handler/registration into one entry with sorted, deduplicated `attacker_inputs`. Emit framework coverage separately:

```python
@dataclass(frozen=True)
class FrameworkCoverage:
    framework: str
    status: Literal["complete", "partial", "unsupported"]
    supported_patterns: tuple[str, ...]
    unsupported_patterns: tuple[str, ...]
    effect_on_verdict: Literal["none", "forces_unknown"]
```

- [ ] **Step 4: Create self-contained framework fixture stubs**

Under each fixture, create only the minimum local classes/annotations needed for CodeQL extraction without Maven downloads:

- Spring: local `Controller`, `RequestMapping`, `RequestBody`, `RequestParam`, and fixture controller.
- Servlet: local `WebServlet`, `HttpServlet`, request/response stubs, and fixture servlet.
- Netty: local `ChannelInitializer`, `ChannelPipeline`, `ChannelInboundHandlerAdapter`, context/channel stubs, and registered/unregistered handlers.
- MQTT: local Paho-like `IMqttMessageListener`, `MqttAsyncClient`, `MqttMessage`, and registered/unregistered listeners.

Each fixture contains one supported registered entry, one unregistered lookalike, and one dynamic/reflection registration gap.

- [ ] **Step 5: Write QL query tests before implementing queries**

`tests/test_codeql_entry_queries.py` should be skipped unless both `DOSWEB_RUN_CODEQL_FIXTURES=1` and `codeql` are available. When enabled, it builds temporary CodeQL databases, runs each query, validates exact columns through Task 3's decoder, and compares normalized semantic facts—not row counts—to expected values.

- [ ] **Step 6: Implement the four entry queries**

Each query uses `@kind table` and emits exactly `ENTRY_COLUMNS`.

Minimum rules:

- Spring MVC: require controller/mapping annotation evidence; merge class/method routes; identify request body/parameter/path/header inputs and materialization phase.
- Servlet: require `@WebServlet` or a specifically modeled static registration; inheritance alone is insufficient.
- Netty: require both a handler callback and a statically recoverable pipeline registration chain.
- MQTT: require a statically recoverable subscribe/callback registration; listener implementation alone is insufficient.

Where a query sees a recognized but unresolved dynamic registration pattern, emit a coverage row marked `partial` with a concrete note. Do not fabricate an externally reachable entry.

- [ ] **Step 7: Run entry unit tests and optional CodeQL fixtures**

Run default tests:

```bash
python -m unittest tests.test_entries -v
```

Expected: all pass without CodeQL.

If CodeQL is installed and the explicit opt-in is intended:

```bash
DOSWEB_RUN_CODEQL_FIXTURES=1 \
python -m unittest tests.test_codeql_entry_queries -v
```

Expected: all four queries compile, exact columns match, registered entries are present, and unregistered lookalikes are absent.

- [ ] **Step 8: Update changelog and checkpoint**

If commits are authorized:

```bash
git add dosweb/entries codeql/dosweb/Entries tests/fixtures tests/test_entries.py tests/test_codeql_entry_queries.py CHANGELOG.md
git commit -m "feat: extract registered Java service entries"
```

---

### Task 5: Extract G1–G4, Build Bounded Slices, and Verify Growth Deterministically

**Files:**
- Create: `codeql/dosweb/Growth/InputMaterialization.ql`
- Create: `codeql/dosweb/Growth/DirectAllocation.ql`
- Create: `codeql/dosweb/Growth/ContainerGrowth.ql`
- Create: `codeql/dosweb/Growth/AsyncWorkGrowth.ql`
- Create: `dosweb/growth/slices.py`
- Create: `dosweb/growth/verify.py`
- Create: `tests/test_growth_verification.py`
- Create: `tests/test_codeql_growth_queries.py`
- Modify: the four Java fixtures with G1–G4 examples
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: entry facts, raw `GROWTH_COLUMNS`, and DeepSeek contracts.
- Produces: normalized `GrowthCandidate`, `build_bounded_slice(...) -> BoundedSlice`, and `verify_growth_contract(...) -> VerifiedGrowthResult` with status `verified|rejected|unresolved`.

- [ ] **Step 1: Write deterministic Growth verification tests**

Fix these outcomes:

```python
# model says no
a result with status="rejected" and reason "GROWTH_CONTRACT_NEGATED"

# valid semantic unknown
a result with status="unresolved" and reason "GROWTH_CONTRACT_UNKNOWN"

# yes but wrong kind/dimension
a result with status="unresolved" and reason "GROWTH_KIND_MISMATCH" or "GROWTH_DIMENSION_MISMATCH"

# required evidence not in slice
a result with status="unresolved" and reason "GROWTH_UNMAPPED_REQUIRED_EVIDENCE"

# cited location outside slice
a result with status="unresolved" and reason "GROWTH_LOCATION_OUTSIDE_SLICE"

# all static mappings proven
a result with status="verified" and a stable verified_growth_id
```

Include one test for each G1–G4 kind and assert that LLM confidence alone never changes the status.

- [ ] **Step 2: Run Growth tests and confirm missing implementation failure**

Run:

```bash
python -m unittest tests.test_growth_verification -v
```

Expected: missing slice/verifier symbols.

- [ ] **Step 3: Implement Growth candidate normalization and bounded slices**

Normalize raw rows into:

```python
@dataclass(frozen=True)
class GrowthCandidate:
    growth_id: str
    site: SourceLocation
    kind: GrowthKind
    operation: str
    resource_id: str
    resource_dimension: ResourceDimension
    receiver: str
    field_path: str
    demand_inputs: tuple[DemandInput, ...]
    escape_scope: EscapeScope
    evidence_ids: frozenset[str]
```

Build a slice containing exactly one entry and one candidate plus only related flow, CFG, receiver/key, registration, and configuration facts. Sort all facts by stable identity and derive `slice_id` from the canonical normalized payload.

- [ ] **Step 4: Implement deterministic contract verification**

`verify_growth_contract(candidate, bounded_slice, contract, static_fact_index)` must:

1. handle `no` and `unknown` first;
2. compare kind and dimension;
3. ensure every required evidence ID belongs to the slice and exists in the static index;
4. ensure every model-cited location belongs to `allowed_locations`;
5. ensure attacker-influence targets correspond to candidate demand roles and static source/sink facts;
6. return `verified` only when all checks pass.

Store the complete reason-code list and check results in `verified_growth.jsonl`; do not discard rejected/unresolved records from the audit trail.

- [ ] **Step 5: Add G1–G4 fixture cases and query tests**

Add to fixtures:

- G1: request/stream body materialization into bytes or object graph.
- G2: attacker-controlled array/buffer size.
- G3: long-lived map/list/registry insertion and one request-local non-escaping negative.
- G4: executor/queue task submission with finite and unbounded queue variants.

The QL tests validate exact `GROWTH_COLUMNS`, location, operation, resource dimension, receiver/field path, demand role, and escape scope. Queries emit candidates only; they never claim verified growth or a verdict.

- [ ] **Step 6: Implement the four Growth queries**

Use shared columns and enums from the design. Keep matching conservative enough for fixtures, and emit explicit `partial` coverage notes for recognized wrappers or dynamic semantics that need the Growth Contract. Do not add ML ranking in P0.

- [ ] **Step 7: Run Growth unit tests and optional query tests**

Run:

```bash
python -m unittest tests.test_growth_verification -v
```

Optional:

```bash
DOSWEB_RUN_CODEQL_FIXTURES=1 \
python -m unittest tests.test_codeql_growth_queries -v
```

Expected: G1–G4 facts match fixture expectations; the request-local collection does not become escaping persistent growth.

- [ ] **Step 8: Update changelog and checkpoint**

If commits are authorized:

```bash
git add dosweb/growth codeql/dosweb/Growth tests/fixtures tests/test_growth_verification.py tests/test_codeql_growth_queries.py CHANGELOG.md
git commit -m "feat: verify four resource growth classes"
```

---

### Task 6: Prove E→G Flows and Evaluate Guard, Bound, and Synchronous Release

**Files:**
- Create: `codeql/dosweb/Flows/EntryToGrowth.ql`
- Create: `codeql/dosweb/Lifecycle/GuardCandidates.ql`
- Create: `codeql/dosweb/Lifecycle/BoundCandidates.ql`
- Create: `codeql/dosweb/Lifecycle/SynchronousReleaseCandidates.ql`
- Create: `dosweb/flows/__init__.py`
- Create: `dosweb/flows/models.py`
- Create: `dosweb/flows/verify.py`
- Create: `dosweb/lifecycle/__init__.py`
- Create: `dosweb/lifecycle/guards.py`
- Create: `dosweb/lifecycle/bounds.py`
- Create: `dosweb/lifecycle/releases.py`
- Create: `tests/test_flow_verification.py`
- Create: `tests/test_lifecycle_guards.py`
- Create: `tests/test_lifecycle_bounds.py`
- Create: `tests/test_lifecycle_releases.py`
- Create: `tests/test_codeql_lifecycle_queries.py`
- Modify: fixtures with valid/invalid lifecycle patterns
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: normalized entries and verified growth.
- Produces: `FlowProof`, `GuardDecision`, `BoundDecision`, and `ReleaseDecision` for Task 7.

- [ ] **Step 1: Write flow proof tests**

Test that a `FlowProof` with `confidence="proven"` and mapped entry/growth IDs verifies, while `partial` remains audit evidence but cannot satisfy a vulnerability premise. Dangling IDs raise `ANALYSIS_DANGLING_FACT_REFERENCE`. Attacker targets are limited to size, key, value, iteration count, and submission count.

- [ ] **Step 2: Write Guard tests with known false-safe patterns**

Create tests for:

- an effective pre-growth, same-dimension, fail-closed dominating Guard;
- `@Size` or handler validation after framework materialization (`GUARD_AFTER_MATERIALIZATION`);
- a check that does not dominate all paths (`GUARD_DOES_NOT_DOMINATE_FLOW`);
- a rejection branch that still reaches G (`GUARD_REJECT_PATH_REACHES_GROWTH`);
- dimension or representation mismatch;
- disabled/unbounded default configuration;
- low-privilege attacker still satisfying an authorization check.

Use decision states `effective|ineffective|unknown` and explicit checks, not a single boolean.

- [ ] **Step 3: Write Bound tests**

Cover all states:

```text
absent
scope_mismatched
dimension_mismatched
possibly_over_budget
effective
unknown
```

Required examples:

- `ArrayBlockingQueue.offer` with checked failure is effective.
- A finite queue whose `offer` result is ignored is not effective.
- `corePoolSize`/`maxPoolSize` does not bound an unbounded executor queue.
- A multipart limit does not bound JSON/raw-body materialization.
- `Content-Length` does not cover chunked requests.
- One-dimensional bounds do not cover multiplicative allocation without a product bound.

- [ ] **Step 4: Write synchronous Release tests**

Cover:

- same receiver/key in a `try/finally`, normal and exceptional path coverage → `synchronous_effective`;
- success-only removal → `insufficient_path_coverage`;
- receiver or key mismatch → `receiver_or_key_mismatched`;
- payload transfer/copy rather than reduction → `unknown` or a stable non-effective reason;
- worker/timer/callback/consumer/ACK → `potential_async`, never effective in P0.

- [ ] **Step 5: Run lifecycle tests and confirm failures**

Run:

```bash
python -m unittest \
  tests.test_flow_verification \
  tests.test_lifecycle_guards \
  tests.test_lifecycle_bounds \
  tests.test_lifecycle_releases -v
```

Expected: missing modules/symbols.

- [ ] **Step 6: Implement flow and lifecycle decisions**

Implement these exact public signatures:

- `verify_flow(flow: FlowProof, entries: Mapping[str, EntryFact], growth: Mapping[str, VerifiedGrowthResult]) -> VerifiedFlow`
- `evaluate_guard(entry: EntryFact, growth: VerifiedGrowthResult, flow: VerifiedFlow, candidates: Sequence[GuardCandidate], configuration: ModeledConfiguration) -> GuardDecision`
- `evaluate_bound(entry: EntryFact, growth: VerifiedGrowthResult, flow: VerifiedFlow, candidates: Sequence[BoundCandidate], configuration: ModeledConfiguration) -> BoundDecision`
- `evaluate_synchronous_release(entry: EntryFact, growth: VerifiedGrowthResult, flow: VerifiedFlow, candidates: Sequence[ReleaseCandidate]) -> ReleaseDecision`

Each decision carries `status`, sorted `reason_codes`, structured checks, evidence IDs, and unresolved facts. Multiple candidates may exist; choose an effective candidate only if all required checks pass. Otherwise preserve the strongest non-effective explanation and all candidate references.

- [ ] **Step 7: Add fixture lifecycle patterns and query tests**

Add valid and invalid Guards, finite/unbounded queues, checked/ignored rejection, matching/mismatching Release, success-only Release, and asynchronous candidates. Query tests assert exact flow/Guard/Bound/Release columns and confirm the QL outputs candidates only.

- [ ] **Step 8: Implement flow and lifecycle queries**

`EntryToGrowth.ql` emits source/sink, target, call path, phase sequence, flow kind, and confidence. Lifecycle queries emit candidates with sufficient CFG, receiver, key, scope, configuration, and coverage hints for Python evaluation. They do not emit `effective`, assertion status, or verdict.

- [ ] **Step 9: Run lifecycle tests and optional CodeQL tests**

Run:

```bash
python -m unittest \
  tests.test_flow_verification \
  tests.test_lifecycle_guards \
  tests.test_lifecycle_bounds \
  tests.test_lifecycle_releases -v
```

Optional:

```bash
DOSWEB_RUN_CODEQL_FIXTURES=1 \
python -m unittest tests.test_codeql_lifecycle_queries -v
```

Expected: all deterministic lifecycle tests pass; potential asynchronous Release remains unresolved.

- [ ] **Step 10: Update changelog and checkpoint**

If commits are authorized:

```bash
git add dosweb/flows dosweb/lifecycle codeql/dosweb/Flows codeql/dosweb/Lifecycle tests/fixtures tests/test_flow_verification.py tests/test_lifecycle_*.py tests/test_codeql_lifecycle_queries.py CHANGELOG.md
git commit -m "feat: evaluate P0 lifecycle evidence"
```

---

### Task 7: Implement Assertions, Certificates, Reports, CLI Orchestration, and Resume

**Files:**
- Create: `dosweb/conclude/__init__.py`
- Create: `dosweb/conclude/assertions.py`
- Create: `dosweb/conclude/verdicts.py`
- Create: `dosweb/lifecycle/certificates.py`
- Create: `dosweb/report/__init__.py`
- Create: `dosweb/report/summary.py`
- Create: `dosweb/report/markdown.py`
- Create: `dosweb/pipeline.py`
- Complete: `dosweb/cli.py`
- Create: `tests/test_assertions.py`
- Create: `tests/test_certificates_and_reports.py`
- Create: `tests/test_pipeline_recovery.py`
- Create: `tests/test_p0_end_to_end.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: all facts and decisions from Tasks 1–6.
- Produces: assertion evaluations, static findings, lifecycle certificates, all designed artifacts, human report, and runnable CLI.

- [ ] **Step 1: Write assertion and verdict tests**

Fix the rules:

```python
# Assertion 1
proven flow + attacker demand + verified growth + no effective Guard + no effective Bound
=> matched

# Assertion 2
proven repeatable flow + attacker-controlled key/value/submission/resource creation
+ escaping verified growth + no effective Bound + no effective synchronous Release
+ no potential asynchronous Release
=> matched
```

Test outcomes:

- either fully matched assertion with no relevant coverage gap → `static_vulnerable`;
- all applicable paths refuted by effective evidence under modeled defaults and no relevant gap → `bounded_under_modeled_assumptions`;
- partial flow, unresolved growth, potential async Release, unknown config, incomplete path coverage, or candidate-relevant coverage gap → `static_unknown`.

Do not allow a high LLM confidence value to enter verdict derivation.

- [ ] **Step 2: Implement assertions and verdict derivation**

Define:

```python
@dataclass(frozen=True)
class AssertionEvaluation:
    assertion: Literal["assertion_1", "assertion_2"]
    status: Literal["matched", "refuted", "unknown", "not_applicable"]
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    unresolved_facts: tuple[str, ...]
```

Implement these exact public functions:

- `evaluate_assertion_1(growth: VerifiedGrowthResult, flow: VerifiedFlow, guard: GuardDecision, bound: BoundDecision) -> AssertionEvaluation`
- `evaluate_assertion_2(growth: VerifiedGrowthResult, flow: VerifiedFlow, bound: BoundDecision, release: ReleaseDecision) -> AssertionEvaluation`
- `derive_verdict(assertions: Sequence[AssertionEvaluation], coverage: CandidateCoverage) -> StaticVerdict`

A bounded verdict must carry assumptions, modeled configuration references, covered entries/paths, and reason codes. Never emit the word `safe` as the verdict.

- [ ] **Step 3: Write certificate and report consistency tests**

A certificate must include entry, attacker input, growth/resource point, proven paths, Guard/Bound/Release decisions, assertion evaluations, assumptions, coverage gaps, unresolved facts, and suggested follow-up measurements. A finding references a `certificate_id`; it must not maintain a divergent copy of lifecycle logic.

Assert that `summary.json` counts, `static_findings.jsonl`, certificate verdicts, and Markdown rows agree exactly by finding ID and verdict.

- [ ] **Step 4: Implement certificates, summary, and Markdown report**

Implement:

- `build_lifecycle_certificate(entry: EntryFact, growth: VerifiedGrowthResult, flows: Sequence[VerifiedFlow], guard: GuardDecision, bound: BoundDecision, release: ReleaseDecision, assertions: Sequence[AssertionEvaluation], coverage: CandidateCoverage, verdict: StaticVerdict) -> LifecycleCertificate`
- `build_summary(findings: Sequence[StaticFinding], coverage: Sequence[FrameworkCoverage]) -> dict[str, object]`
- `render_report(summary: Mapping[str, object], findings: Sequence[StaticFinding], certificates: Sequence[LifecycleCertificate]) -> str`

The report states “static finding” and “bounded under modeled assumptions”; it never says “dynamically confirmed”. Include coverage and limitation sections even when there are no vulnerable findings.

- [ ] **Step 5: Write pipeline recovery tests**

Use fake CodeQL and fake Growth classifier implementations with counters. Assert:

- stage order is `entries -> growth -> flows -> lifecycle -> conclude -> report`;
- a provider failure stops before `verified_growth.jsonl` and downstream artifacts publish;
- successful `--resume` repeats neither CodeQL nor LLM calls;
- changing database fingerprint invalidates entries and all downstream stages;
- changing prompt/schema/model invalidates growth and downstream stages but can reuse entries;
- changing report implementation invalidates report only;
- partial temporary files do not replace prior complete artifacts;
- `run.json` is updated last and records the terminal error code on failure.

- [ ] **Step 6: Implement the stage pipeline**

`Pipeline.run()` owns these stages:

```python
STAGES = ("entries", "growth", "flows", "lifecycle", "conclude", "report")
```

For every stage:

1. compute `StageFingerprint`;
2. reuse only when `--resume` and all fingerprint/output checks pass;
3. validate upstream artifacts and references;
4. write all outputs atomically;
5. publish stage metadata;
6. update `run.json` last.

The `growth` stage invokes DeepSeek for every candidate requiring a Growth Contract. Because DeepSeek is mandatory for P0, any failed required call fails the run; a valid semantic unknown is written as unresolved and processing continues.

- [ ] **Step 7: Complete the CLI**

Support:

```text
dos-web-analyzer analyze
dos-web-analyzer entries
dos-web-analyzer growth
dos-web-analyzer flows
dos-web-analyzer lifecycle
dos-web-analyzer conclude
dos-web-analyzer report
```

Common arguments include database, output, config, model, base URL, CodeQL binary, cache dir, and resume. Translate `AnalyzerError.exit_status` to process status and write one concise sanitized error to stderr. `static_unknown` still exits `0` when analysis completes.

- [ ] **Step 8: Write the network-free P0 end-to-end scenarios**

Use fake query results and a local mock provider to cover:

1. unbounded body/parser materialization;
2. attacker-controlled direct allocation;
3. global map accumulation under distinct keys;
4. an unbounded executor queue;
5. a finite queue with checked rejection;
6. a Guard after materialization;
7. success-only Release;
8. a potential async consumer forcing unknown;
9. a Netty registered handler;
10. an MQTT registered callback.

For every scenario, parse all artifacts strictly and verify ID/reference integrity, certificate completeness, expected verdict, report consistency, and no dynamic execution.

- [ ] **Step 9: Run assertion, report, pipeline, and E2E tests**

Run:

```bash
python -m unittest \
  tests.test_assertions \
  tests.test_certificates_and_reports \
  tests.test_pipeline_recovery \
  tests.test_p0_end_to_end -v
```

Expected: all pass with no external network and no CodeQL installation requirement.

- [ ] **Step 10: Smoke-test CLI help and compilation**

Run:

```bash
python -m compileall dosweb scripts
./dos-web-analyzer --help
./dos-web-analyzer analyze --help
```

Expected: compilation succeeds; both help commands exit `0` and list documented commands/options.

- [ ] **Step 11: Update changelog and checkpoint**

If commits are authorized:

```bash
git add dosweb/conclude dosweb/lifecycle/certificates.py dosweb/report dosweb/pipeline.py dosweb/cli.py tests/test_assertions.py tests/test_certificates_and_reports.py tests/test_pipeline_recovery.py tests/test_p0_end_to_end.py CHANGELOG.md
git commit -m "feat: add resumable P0 analysis conclusions"
```

---

### Task 8: Migrate Active Verdict Consumers, Documentation, and Final Verification

**Files:**
- Modify: `scripts/aggregate_java_web_dos_batch.py`
- Modify: `scripts/prepare_dynamic_validation_output.py`
- Modify: `tests/test_static_codeql_infrastructure.py`
- Modify: `tests/test_dynamic_validation_helpers.py`
- Create: `tests/test_verdict_migration.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CHANGELOG.md`
- Track after authorization: `docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md`
- Track after authorization: `docs/superpowers/plans/2026-07-18-java-web-dos-p0-analyzer.md`

**Interfaces:**
- Consumes: final P0 verdict vocabulary and artifacts.
- Produces: consistent active tooling and documentation with no legacy compatibility path.

- [ ] **Step 1: Write verdict migration regression tests**

Update existing tests and add `tests/test_verdict_migration.py` to assert:

```python
STATIC_VERDICTS == {
    "static_vulnerable",
    "bounded_under_modeled_assumptions",
    "static_unknown",
}
```

Required behavior:

- batch aggregation accepts and counts `bounded_under_modeled_assumptions`;
- batch aggregation rejects `static_safe` with source path and line;
- dynamic scaffold preparation accepts the new static verdict and preserves it only as traceability metadata;
- dynamic status/verdict state remains independent and unchanged;
- active Python modules, README, and AGENTS contain no ordinary-scan `static_safe` token.

Exclude preserved historical specs, PoCs, and result archives from the terminology scan.

- [ ] **Step 2: Run migration tests and confirm old vocabulary failures**

Run:

```bash
python -m unittest \
  tests.test_static_codeql_infrastructure \
  tests.test_dynamic_validation_helpers \
  tests.test_verdict_migration -v
```

Expected: failures showing old `static_safe` acceptance/documentation.

- [ ] **Step 3: Migrate active scripts atomically**

Replace static verdict sets in both scripts with:

```python
STATIC_VERDICTS = {
    "static_vulnerable",
    "bounded_under_modeled_assumptions",
    "static_unknown",
}
```

Do not accept aliases. The dynamic helper may copy the new static verdict into its source-trace block, but must not derive `confirmed`, `not_confirmed`, or any dynamic status from it. Keep its paused/blocked defaults and overwrite protections unchanged.

- [ ] **Step 4: Update README and AGENTS**

README must document:

- Python 3.11 and installation;
- CodeQL and DeepSeek environment requirements;
- one complete `analyze` example;
- internal stage commands and `--resume`;
- output artifact layout;
- exact three-value verdict meanings;
- Spring MVC/Servlet/Netty/MQTT P0 scope;
- assertions 1 and 2 and the asynchronous Release limitation;
- coverage gaps forcing unknown;
- network-free default tests and explicit opt-ins;
- static/dynamic separation.

AGENTS must replace the output vocabulary, state that P0 does not prove asynchronous Release, and preserve all protected-asset and no-dynamic-execution rules. Do not rewrite the historical 2026-07-02 design to pretend it used the new vocabulary.

- [ ] **Step 5: Run all regression and terminology tests**

Run:

```bash
python -m unittest discover -s tests -v
rg -n "static_safe" \
  AGENTS.md README.md dosweb scripts \
  --glob '!docs/superpowers/specs/2026-07-02-java-web-dos-v2-rewrite-design.md'
```

Expected: all tests pass; `rg` returns no active-code/document matches.

- [ ] **Step 6: Run CodeQL pack and optional fixture verification**

When CodeQL is installed:

```bash
codeql pack install codeql
DOSWEB_RUN_CODEQL_FIXTURES=1 \
python -m unittest \
  tests.test_codeql_entry_queries \
  tests.test_codeql_growth_queries \
  tests.test_codeql_lifecycle_queries -v
```

Expected: pack installation succeeds; all framework queries compile and match normalized fixture facts. If CodeQL is unavailable, report this verification as skipped rather than claiming it passed.

- [ ] **Step 7: Run final product verification**

Run:

```bash
python -m compileall dosweb scripts
python -m unittest discover -s tests -v
git diff --check
git status --short
```

Expected:

- compilation succeeds;
- all default tests pass with no external network;
- no whitespace errors;
- only intended implementation, tests, docs, approved spec/plan, and changelog changes remain;
- protected assets and historical result directories are untouched.

- [ ] **Step 8: Update final changelog verification and checkpoint**

Record exact test counts, whether CodeQL fixture verification ran or was skipped, and that no real DeepSeek or dynamic DoS execution occurred.

If commits are authorized, explicitly force-add the ignored approved documents and create the final migration/docs commit:

```bash
git add scripts/aggregate_java_web_dos_batch.py scripts/prepare_dynamic_validation_output.py \
  tests/test_static_codeql_infrastructure.py tests/test_dynamic_validation_helpers.py \
  tests/test_verdict_migration.py README.md AGENTS.md CHANGELOG.md
git add -f docs/superpowers/specs/2026-07-18-java-web-dos-p0-analyzer-design.md \
  docs/superpowers/plans/2026-07-18-java-web-dos-p0-analyzer.md
git commit -m "feat: migrate active tooling to bounded static verdicts"
```

- [ ] **Step 9: Request code review before integration**

Invoke `superpowers:requesting-code-review`, then address only verified findings. Re-run Task 8 Step 7 after every accepted fix. Do not merge, push, or open a PR unless the user separately asks.

---

## Dependency Graph

```text
Task 1  package/config/artifacts
  |\
  | +--> Task 2  DeepSeek contract/cache
  |
  +----> Task 3  CodeQL runner/decoder
             |
             +--> Task 4  registered entries
                       |
Task 2 ---------------+--> Task 5  G1-G4 + bounded-slice verification
                                  |
                                  +--> Task 6  flows + lifecycle decisions
                                               |
                                               +--> Task 7  assertions/pipeline/reports
                                                            |
                                                            +--> Task 8  migration/final verification
```

Tasks 2 and 3 may be implemented in parallel after Task 1. Tasks 4–8 are sequential because each freezes interfaces consumed by the next task.

## Completion Evidence

Do not claim P0 complete until evidence shows:

- all default `unittest` tests pass without external network;
- real CodeQL fixture tests pass, or are explicitly reported as not run because CodeQL is unavailable;
- the four baseline framework entry models produce registered entries and visible gaps;
- G1–G4 candidates pass through both the Growth Contract and deterministic verification;
- only proven attacker-controlled flows can support vulnerable conclusions;
- Guard, Bound, and synchronous Release false-safe patterns are covered by regression tests;
- assertion 1 and assertion 2 produce complete lifecycle certificates;
- relevant asynchronous Release evidence forces `static_unknown`;
- `bounded_under_modeled_assumptions` includes assumptions and coverage;
- CLI resume avoids duplicate CodeQL and provider work when fingerprints match;
- active tooling and documentation contain no `static_safe` compatibility path;
- ordinary analysis performs no dynamic DoS execution and consumes no dynamic truth as static verdict evidence.
