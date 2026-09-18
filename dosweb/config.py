from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import stat
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

from dosweb.configuration.policy import modeled_key_allowed, normalize_modeled_value
from dosweb.errors import AnalyzerError


DEFAULT_BASE_URL = "https://rightapi.ai/grok/v1/"
DEFAULT_MODEL = "grok-4.6"
SUPPORTED_MODELS = frozenset({"grok-4.6"})
RESPONSE_MODEL_ALIASES = {"grok-4.6": frozenset({"grok-4.6", "grok-4.6-build"})}


def model_response_matches(requested: str, actual: str) -> bool:
    return actual in RESPONSE_MODEL_ALIASES.get(requested, frozenset({requested}))
MAX_LLM_RETRIES = 5
MAX_LLM_TIMEOUT_SECONDS = 300
_MAX_CONFIG_NESTING = 128
_MAX_CONFIG_BYTES = 262144
_MAX_CONFIG_NODES = 4096
_MAX_CONFIG_COLLECTION = 256
_MAX_CONFIG_STRING_BYTES = 65536
_DEFAULT_SECRETS_PATH = Path(__file__).resolve().parent.parent / "config" / "local_secrets.json"
_MAX_SECRETS_BYTES = 4096
_ROOT_CONFIG_KEYS = frozenset({"llm", "cache_dir", "codeql_binary", "resume", "allow_partial_codeql", "analysis"})
_ANALYSIS_CONFIG_KEYS = frozenset({"modeled_defaults"})
_LLM_CONFIG_KEYS = frozenset({"model", "base_url", "timeout_seconds", "max_retries", "temperature", "allow_remote_llm", "public_source_url", "source_commit_sha", "source_checkout", "analysis_source_root"})


@dataclass(frozen=True)
class LlmConfig:
    model: str
    base_url: str
    api_key: str
    timeout_seconds: int
    max_retries: int
    temperature: float
    cache_dir: Path
    allow_remote_llm: bool = False
    public_source_url: str | None = None
    source_commit_sha: str | None = None
    source_checkout: Path | None = None
    analysis_source_root: Path | None = None


@dataclass(frozen=True)
class AnalyzerConfig:
    database: Path
    output: Path
    llm: LlmConfig
    codeql_binary: str
    resume: bool
    # This is deliberately entries-only and changes formal artifact identity.
    allow_partial_codeql: bool = False
    modeled_defaults: Mapping[str, str | int | bool] = ()


class _StrictConfigLoader(yaml.SafeLoader):
    def compose_node(self, parent: object, index: object) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("configuration aliases are not supported")
        node = super().compose_node(parent, index)
        allowed = {
            "tag:yaml.org,2002:null", "tag:yaml.org,2002:bool", "tag:yaml.org,2002:int",
            "tag:yaml.org,2002:float", "tag:yaml.org,2002:str", "tag:yaml.org,2002:seq",
            "tag:yaml.org,2002:map",
        }
        if node.tag not in allowed:
            raise yaml.YAMLError("unsupported configuration tag")
        return node

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[object, object]:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=False)
            try:
                duplicate = key in seen
                seen.add(key)
            except TypeError as exc:
                raise yaml.YAMLError("unhashable configuration key") from exc
            if duplicate:
                raise yaml.YAMLError("duplicate configuration key")
        return super().construct_mapping(node, deep=deep)


def _bounded_config_bytes(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_CONFIG_BYTES:
            raise ValueError("configuration is not a bounded regular file")
        data = bytearray()
        while len(data) <= _MAX_CONFIG_BYTES:
            chunk = os.read(descriptor, _MAX_CONFIG_BYTES + 1 - len(data))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > _MAX_CONFIG_BYTES:
            raise ValueError("configuration file exceeds byte limit")
        return bytes(data)
    finally:
        os.close(descriptor)


def _load_yaml(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        raw = _bounded_config_bytes(path)
        parsed = yaml.load(raw.decode("utf-8"), Loader=_StrictConfigLoader)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, RecursionError, ValueError, MemoryError) as exc:
        raise AnalyzerError(
            "CONFIG_INVALID_FILE",
            "Could not read configuration file.",
            {"path": str(path)},
        ) from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration root must be an object.")
    _validate_config_shape(parsed, path)
    _reject_unknown_keys(parsed)
    return parsed


def _validate_config_shape(value: object, path: Path, *, depth: int = 0, counter: list[int] | None = None) -> None:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > _MAX_CONFIG_NODES:
        raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration is too large.", {"path": str(path)})
    if depth > _MAX_CONFIG_NESTING:
        raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration nesting is too deep.", {"path": str(path)})
    if isinstance(value, str):
        try:
            if len(value.encode("utf-8")) > _MAX_CONFIG_STRING_BYTES:
                raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration string is too large.", {"path": str(path)})
        except UnicodeEncodeError as exc:
            raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration contains invalid Unicode.", {"path": str(path)}) from exc
        return
    if isinstance(value, Mapping):
        if len(value) > _MAX_CONFIG_COLLECTION:
            raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration collection is too large.", {"path": str(path)})
        for key, nested in value.items():
            if not isinstance(key, str):
                raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration key must be a string.", {"path": str(path)})
            try:
                key.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration contains invalid Unicode.", {"path": str(path)}) from exc
            if _normalise_config_key(key) == "apikey":
                raise AnalyzerError("CONFIG_SECRET_IN_FILE", "API keys must not appear in configuration files.", {"path": str(path)})
            _validate_config_shape(nested, path, depth=depth + 1, counter=counter)
        return
    if isinstance(value, list):
        if len(value) > _MAX_CONFIG_COLLECTION:
            raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration collection is too large.", {"path": str(path)})
        for nested in value:
            _validate_config_shape(nested, path, depth=depth + 1, counter=counter)
        return
    if isinstance(value, (type(None), bool, int, float)):
        return
    raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration contains an unsupported value.", {"path": str(path)})


def _reject_unknown_keys(config: Mapping[str, object]) -> None:
    if any(not isinstance(key, str) or key not in _ROOT_CONFIG_KEYS for key in config):
        raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration contains an unknown root key.")
    llm = config.get("llm", {})
    if not isinstance(llm, Mapping):
        raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration llm section must be an object.")
    if any(not isinstance(key, str) or key not in _LLM_CONFIG_KEYS for key in llm):
        raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration contains an unknown llm key.")


def _normalise_config_key(key: str) -> str:
    return "".join(character.lower() for character in key if character.isalnum())


def _yaml_llm(config: Mapping[str, Any]) -> Mapping[str, Any]:
    value = config.get("llm", {})
    if not isinstance(value, Mapping):
        raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration llm section must be an object.")
    return value


def _value(
    cli_values: Mapping[str, object],
    name: str,
    yaml_values: Mapping[str, Any],
    default: object,
) -> object:
    cli_value = cli_values.get(name)
    if cli_value is not None:
        return cli_value
    if name in yaml_values:
        return yaml_values[name]
    return default


def _normalise_base_url(value: object) -> str:
    try:
        if not isinstance(value, str):
            raise ValueError
        parsed = urlsplit(value)
        raw_authority = parsed.netloc
        if (
            not raw_authority or "@" in raw_authority or raw_authority.endswith(":")
            or parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment
        ):
            raise ValueError
        host = parsed.hostname.lower()
        port = parsed.port
        rendered_host = f"[{host}]" if ":" in host else host
        netloc = rendered_host if port is None else f"{rendered_host}:{port}"
        return urlunsplit((parsed.scheme.lower(), netloc, f"{parsed.path.rstrip('/')}/", "", ""))
    except (TypeError, ValueError, OverflowError) as exc:
        raise AnalyzerError("CONFIG_INVALID_VALUE", "llm.base_url must be a valid HTTP(S) URL.") from exc


def _read_local_api_key(path: Path) -> str:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return ""
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size > _MAX_SECRETS_BYTES
        ):
            raise AnalyzerError(
                "CONFIG_SECRET_FILE_UNSAFE",
                "Local secrets file must be an owner-only bounded regular file.",
                {"path": str(path)},
            )
        data = bytearray()
        while len(data) <= _MAX_SECRETS_BYTES:
            chunk = os.read(descriptor, _MAX_SECRETS_BYTES + 1 - len(data))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > _MAX_SECRETS_BYTES:
            return ""
    finally:
        os.close(descriptor)
    try:
        payload = json.loads(bytes(data).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalyzerError("CONFIG_INVALID_FILE", "Local secrets file is not valid JSON.", {"path": str(path)}) from exc
    if not isinstance(payload, dict):
        raise AnalyzerError("CONFIG_INVALID_FILE", "Local secrets file root must be an object.", {"path": str(path)})
    value = payload.get("deepseek_api_key", "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise AnalyzerError("CONFIG_INVALID_FILE", "Local secrets deepseek_api_key must be a string.", {"path": str(path)})
    return value.strip()


def resolve_api_key(environ: Mapping[str, str], secrets_path: Path | None = None) -> str:
    """Resolve the provider API key: environment first, then a local secrets file."""
    key = environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    if secrets_path is not None:
        return _read_local_api_key(secrets_path)
    return ""


def load_config(
    cli_values: Mapping[str, object],
    config_path: Path | None,
    environ: Mapping[str, str],
    *,
    secrets_path: Path | None = None,
) -> AnalyzerConfig:
    yaml_config = _load_yaml(config_path)
    yaml_llm = _yaml_llm(yaml_config)
    analysis = yaml_config.get("analysis", {})
    if not isinstance(analysis, Mapping) or set(analysis) - _ANALYSIS_CONFIG_KEYS:
        raise AnalyzerError("CONFIG_INVALID_FILE", "analysis configuration contains unsupported fields.")
    configured_raw = analysis.get("modeled_defaults", {})
    if not isinstance(configured_raw, Mapping) or len(configured_raw) > _MAX_CONFIG_COLLECTION:
        raise AnalyzerError("CONFIG_INVALID_FILE", "analysis.modeled_defaults must be a bounded non-secret mapping.")
    configured_defaults: dict[str, str | int | bool] = {}
    for key, value in configured_raw.items():
        if not modeled_key_allowed(key):
            raise AnalyzerError("CONFIG_INVALID_FILE", "analysis.modeled_defaults contains a sensitive or irrelevant key.")
        normalized = normalize_modeled_value(key, value)
        if normalized is None:
            raise AnalyzerError("CONFIG_INVALID_FILE", "analysis.modeled_defaults contains a non-public value.")
        configured_defaults[key] = normalized
    cli_defaults = _modeled_default_overrides(cli_values.get("modeled_default"))

    allow_remote_llm = _boolean(
        _value(cli_values, "allow_remote_llm", yaml_llm, False), "allow_remote_llm"
    )
    api_key = resolve_api_key(environ, secrets_path)
    if allow_remote_llm and not api_key:
        raise AnalyzerError(
            "CONFIG_MISSING_DEEPSEEK_API_KEY",
            "Provider API key must be set in the environment or config/local_secrets.json.",
        )

    model = _value(cli_values, "model", yaml_llm, DEFAULT_MODEL)
    if not isinstance(model, str) or model not in SUPPORTED_MODELS:
        raise AnalyzerError("CONFIG_UNSUPPORTED_MODEL", "Unsupported LLM model.")
    base_url = _normalise_base_url(
        _value(
            cli_values,
            "base_url",
            yaml_llm,
            environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
        )
    )

    output = cli_values.get("output")
    database = cli_values.get("database")
    if not isinstance(output, Path) or not isinstance(database, Path):
        raise AnalyzerError("CONFIG_INVALID_VALUE", "database and output paths are required.")

    cache_dir = _path(_value(cli_values, "cache_dir", yaml_config, output / "cache" / "llm"), "cache_dir")

    public_source_url = _canonical_public_source_url(
        _value(cli_values, "public_source_url", yaml_llm, None)
    )
    source_commit_sha = _optional_non_empty_string(
        _value(cli_values, "source_commit_sha", yaml_llm, None), "source_commit_sha"
    )
    source_checkout = _optional_path(
        _value(cli_values, "source_checkout", yaml_llm, None), "source_checkout"
    )
    analysis_source_root = _optional_path(
        _value(cli_values, "analysis_source_root", yaml_llm, source_checkout), "analysis_source_root"
    )
    for source_root in (analysis_source_root, source_checkout):
        if source_root is None:
            continue
        try:
            relative_output = output.resolve(strict=False).relative_to(source_root.resolve(strict=False))
        except ValueError:
            continue
        except (OSError, RuntimeError) as exc:
            raise AnalyzerError("CONFIG_INVALID_VALUE", "Source and output paths could not be resolved.") from exc
        if relative_output.parts[:2] == ("results", "applications_static_analysis"):
            raise AnalyzerError(
                "CONFIG_OUTPUT_INSIDE_SOURCE",
                "Analyzer output must not be written into the source snapshot's analyzer-results subtree.",
            )

    timeout_seconds = _bounded_int(_value(cli_values, "timeout_seconds", yaml_llm, 60), "timeout_seconds", 1, MAX_LLM_TIMEOUT_SECONDS)
    max_retries = _bounded_int(
        _value(cli_values, "max_retries", yaml_llm, 3), "max_retries", 1, MAX_LLM_RETRIES
    )
    temperature = _temperature(_value(cli_values, "temperature", yaml_llm, 0))

    return AnalyzerConfig(
        database=database,
        output=output,
        llm=LlmConfig(
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            temperature=temperature,
            cache_dir=cache_dir,
            allow_remote_llm=allow_remote_llm,
            public_source_url=public_source_url,
            source_commit_sha=source_commit_sha,
            source_checkout=source_checkout,
            analysis_source_root=analysis_source_root,
        ),
        codeql_binary=_string(
            _value(cli_values, "codeql_binary", yaml_config, "codeql"), "codeql_binary"
        ),
        resume=_boolean(_value(cli_values, "resume", yaml_config, False), "resume"),
        allow_partial_codeql=_boolean(
            _value(cli_values, "allow_partial_codeql", yaml_config, False),
            "allow_partial_codeql",
        ),
        modeled_defaults={**dict(configured_defaults), **cli_defaults},
    )


def _modeled_default_overrides(raw: object) -> dict[str, str | int | bool]:
    if raw is None:
        return {}
    if not isinstance(raw, (list, tuple)) or len(raw) > _MAX_CONFIG_COLLECTION:
        raise AnalyzerError("CONFIG_INVALID_VALUE", "--modeled-default must be repeated key=value.")
    result: dict[str, str | int | bool] = {}
    for item in raw:
        if not isinstance(item, str) or item.count("=") != 1:
            raise AnalyzerError("CONFIG_INVALID_VALUE", "--modeled-default must be key=value.")
        key, value = item.split("=", 1)
        if key in result or not modeled_key_allowed(key):
            raise AnalyzerError("CONFIG_INVALID_VALUE", "--modeled-default contains a sensitive, irrelevant, or duplicate key.")
        normalized = normalize_modeled_value(key, value)
        if normalized is None:
            raise AnalyzerError("CONFIG_INVALID_VALUE", "--modeled-default contains a non-public value.")
        result[key] = normalized
    return result


def _positive_int(value: object, name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AnalyzerError("CONFIG_INVALID_VALUE", f"{name} has an invalid value.")
    return value


def _bounded_int(value: object, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise AnalyzerError("CONFIG_INVALID_VALUE", f"{name} has an invalid value.")
    return value


def _temperature(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 2:
        raise AnalyzerError("CONFIG_INVALID_VALUE", "temperature has an invalid value.")
    return float(value)


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise AnalyzerError("CONFIG_INVALID_VALUE", f"{name} must be a non-empty string.")
    return value


def _canonical_public_source_url(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise AnalyzerError("CONFIG_INVALID_VALUE", "public_source_url must be a non-empty string.")
    return value.rstrip("/")


def _optional_non_empty_string(value: object, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AnalyzerError("CONFIG_INVALID_VALUE", f"{name} must be a non-empty string.")
    return value


def _path(value: object, name: str) -> Path:
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value.strip():
        return Path(value)
    raise AnalyzerError("CONFIG_INVALID_VALUE", f"{name} must be a path.")


def _optional_path(value: object, name: str) -> Path | None:
    if value is None:
        return None
    return _path(value, name)


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise AnalyzerError("CONFIG_INVALID_VALUE", f"{name} must be a boolean.")
    return value
