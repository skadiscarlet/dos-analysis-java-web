from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
import os
from pathlib import Path
import stat
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

from dosweb.errors import AnalyzerError


DEFAULT_BASE_URL = "https://api.deepseek.com/"
DEFAULT_MODEL = "deepseek-v4-pro"
SUPPORTED_MODELS = frozenset({"deepseek-v4-pro", "deepseek-v4-flash"})
MAX_LLM_RETRIES = 5
MAX_LLM_TIMEOUT_SECONDS = 300
_MAX_CONFIG_NESTING = 128
_MAX_CONFIG_BYTES = 262144
_MAX_CONFIG_NODES = 4096
_MAX_CONFIG_COLLECTION = 256
_MAX_CONFIG_STRING_BYTES = 65536
_ROOT_CONFIG_KEYS = frozenset({"llm", "cache_dir", "codeql_binary", "resume"})
_LLM_CONFIG_KEYS = frozenset({"model", "base_url", "timeout_seconds", "max_retries", "temperature", "allow_remote_llm", "public_source_url", "source_commit_sha", "source_checkout"})


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


@dataclass(frozen=True)
class AnalyzerConfig:
    database: Path
    output: Path
    llm: LlmConfig
    codeql_binary: str
    resume: bool


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
    try:
        _reject_api_key(parsed)
        _reject_unknown_keys(parsed)
    except UnicodeEncodeError as exc:
        raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration contains invalid Unicode.", {"path": str(path)}) from exc
    return parsed


def _reject_api_key(value: object) -> None:
    visited: set[int] = set()
    stack: list[tuple[object, int]] = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_CONFIG_NODES:
            raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration contains too many values.")
        if depth > _MAX_CONFIG_NESTING:
            raise AnalyzerError(
                "CONFIG_INVALID_FILE",
                "Configuration nesting exceeds the supported maximum.",
            )
        if isinstance(current, str) and len(current.encode("utf-8")) > _MAX_CONFIG_STRING_BYTES:
            raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration string exceeds the supported maximum.")
        if not isinstance(current, (Mapping, list)):
            continue
        if len(current) > _MAX_CONFIG_COLLECTION:
            raise AnalyzerError("CONFIG_INVALID_FILE", "Configuration collection exceeds the supported maximum.")
        identity = id(current)
        if identity in visited:
            raise AnalyzerError(
                "CONFIG_INVALID_FILE",
                "Configuration contains recursive or aliased collections.",
            )
        visited.add(identity)
        if isinstance(current, Mapping):
            for key, nested in current.items():
                if isinstance(key, str) and _normalise_config_key(key) == "apikey":
                    raise AnalyzerError(
                        "CONFIG_SECRET_IN_FILE",
                        "Configuration files must not contain API key values.",
                    )
                stack.append((nested, depth + 1))
        else:
            for nested in current:
                stack.append((nested, depth + 1))


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


def load_config(
    cli_values: Mapping[str, object],
    config_path: Path | None,
    environ: Mapping[str, str],
) -> AnalyzerConfig:
    yaml_config = _load_yaml(config_path)
    yaml_llm = _yaml_llm(yaml_config)

    allow_remote_llm = _boolean(
        _value(cli_values, "allow_remote_llm", yaml_llm, False), "allow_remote_llm"
    )
    api_key = environ.get("DEEPSEEK_API_KEY", "")
    if allow_remote_llm and not api_key.strip():
        raise AnalyzerError(
            "CONFIG_MISSING_DEEPSEEK_API_KEY",
            "DEEPSEEK_API_KEY must be set to a non-empty value in the environment.",
        )

    model = _value(cli_values, "model", yaml_llm, DEFAULT_MODEL)
    if not isinstance(model, str) or model not in SUPPORTED_MODELS:
        raise AnalyzerError("CONFIG_UNSUPPORTED_MODEL", "Unsupported DeepSeek model.")
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
        ),
        codeql_binary=_string(
            _value(cli_values, "codeql_binary", yaml_config, "codeql"), "codeql_binary"
        ),
        resume=_boolean(_value(cli_values, "resume", yaml_config, False), "resume"),
    )


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
