from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml

from dosweb.configuration.models import ModeledConfigurationFact
from dosweb.configuration.policy import modeled_key_allowed, normalize_modeled_value
from dosweb.errors import AnalyzerError

_MAX_FILES = 128
_MAX_VISITED_ENTRIES = 100_000
_MAX_FILE_BYTES = 256 * 1024
_ALLOWED = {"application.properties", "application.yml", "application.yaml", "web.xml"}
_MAX_YAML_NODES = 4096
_MAX_YAML_DEPTH = 64
# Generated or dependency directories are never configuration sources.  This is the
# same exclusion vocabulary used by the canonical corpus tree fingerprint, so walking
# cannot be defeated by vendored node_modules or build output.
_EXCLUDED_DIRS = frozenset({".agents", ".git", ".gradle", ".idea", ".mvn", "build", "node_modules", "out", "target"})
_MAX_PRUNED_SAMPLE = 256
_CONFIG_ROOT_DIRS = frozenset({"config", "conf", "WEB-INF"})


class _BoundedYamlLoader(yaml.SafeLoader):
    def compose_node(self, parent: object, index: object) -> yaml.Node:
        nodes = getattr(self, "_dosweb_nodes", 0) + 1
        depth = getattr(self, "_dosweb_depth", 0) + 1
        if nodes > _MAX_YAML_NODES or depth > _MAX_YAML_DEPTH or self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("configuration YAML exceeds safe structural limits")
        self._dosweb_nodes = nodes
        self._dosweb_depth = depth
        try:
            return super().compose_node(parent, index)
        finally:
            self._dosweb_depth = depth - 1


def _fail() -> None:
    raise AnalyzerError("CONFIG_MODELED_DEFAULT_INVALID", "Modeled defaults must be bounded, source-root-contained values.")


def _config_in_scope(root: Path, candidate: Path) -> bool:
    """Only root, config/conf/WEB-INF, and module src/main/resources are modeled sources."""
    try:
        parent = candidate.parent.relative_to(root)
    except ValueError:
        return False
    parts = parent.parts
    if not parts:
        return True
    if parts[-1] in _CONFIG_ROOT_DIRS:
        return True
    if len(parts) >= 3 and parts[-3:] == ("src", "main", "resources"):
        return True
    return False


def _new_configuration_coverage() -> dict[str, object]:
    return {
        "schema_version": 1,
        "visited_entries": 0,
        "pruned_directory_entries": 0,
        "pruned_directories": [],
        "config_files_read": 0,
        "config_files_skipped_out_of_scope": 0,
        "excluded_directory_names": sorted(_EXCLUDED_DIRS),
        "max_visited_entries": _MAX_VISITED_ENTRIES,
        "max_config_files": _MAX_FILES,
        "truncated": False,
    }


def _read(path: Path) -> str:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_FILE_BYTES:
                _fail()
            data = os.read(fd, _MAX_FILE_BYTES + 1)
        finally:
            os.close(fd)
        if len(data) > _MAX_FILE_BYTES:
            _fail()
        return data.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise AnalyzerError("CONFIG_MODELED_DEFAULT_INVALID", "Unable to read modeled default safely.") from exc


def _unknown(key: str, path: str, line: int) -> ModeledConfigurationFact:
    return ModeledConfigurationFact(key, None, path, line, "unknown", "unknown", False, "unknown")


def _properties(content: str, path: str) -> Iterable[ModeledConfigurationFact]:
    seen: set[str] = set()
    for line_no, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "!")):
            continue
        if "=" not in stripped and ":" not in stripped:
            continue
        key, value = re.split(r"[=:]", stripped, maxsplit=1)
        key = key.strip()
        if not modeled_key_allowed(key):
            continue
        if key in seen:
            yield _unknown(key, path, line_no)
            continue
        seen.add(key)
        parsed = normalize_modeled_value(key, value)
        yield _unknown(key, path, line_no) if parsed is None else ModeledConfigurationFact(key, parsed, path, line_no, "default", "extracted_default", True, "known")


def _yaml(content: str, path: str) -> Iterable[ModeledConfigurationFact]:
    try:
        raw = yaml.load(content, Loader=_BoundedYamlLoader)
    except yaml.YAMLError:
        yield _unknown("yaml_parse", path, 0); return
    if not isinstance(raw, Mapping):
        yield _unknown("yaml_root", path, 0); return
    def walk(value: object, prefix: str = "") -> Iterable[tuple[str, object]]:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if not isinstance(key, str):
                    continue
                yield from walk(child, f"{prefix}.{key}" if prefix else key)
        else:
            yield prefix, value
    for key, value in walk(raw):
        # profiles and placeholders are not default-effective without a full environment model.
        if key.startswith("spring.profiles") or not modeled_key_allowed(key):
            continue
        normalized = normalize_modeled_value(key, value)
        if normalized is not None:
            yield ModeledConfigurationFact(key, normalized, path, 0, "default", "extracted_default", True, "known")
        else:
            yield _unknown(key, path, 0)


def _webxml(content: str, path: str) -> Iterable[ModeledConfigurationFact]:
    # Preserve security constraint presence as unknown: mapping it to a concrete auth role requires route matching.
    if "<security-constraint" in content:
        yield _unknown("servlet.security_constraint", path, content.index("<security-constraint") + 1)


def _extract_modeled_configuration(
    source_root: Path,
    overrides: Mapping[str, str | int | bool] | None,
    coverage: dict[str, object],
) -> list[dict[str, object]]:
    """Extract finite defaults only; symlinks, duplicate keys and uncertain profiles stay unknown."""
    root = source_root.resolve(strict=True)
    if not root.is_dir():
        _fail()
    records: list[ModeledConfigurationFact] = []
    count = 0
    visited = 0
    pruned = 0
    sample_truncated = False
    for current, directories, files in os.walk(root, followlinks=False):
        visited += len(directories) + len(files)
        if visited > _MAX_VISITED_ENTRIES:
            _fail()
        kept: list[str] = []
        for name in directories:
            entry = Path(current) / name
            if entry.is_symlink() or name in _EXCLUDED_DIRS:
                pruned += 1
                sample = coverage["pruned_directories"]
                if len(sample) >= _MAX_PRUNED_SAMPLE:
                    sample_truncated = True
                else:
                    try:
                        relative = entry.relative_to(root).as_posix()
                    except ValueError:
                        relative = name
                    sample.append({"path": relative, "reason": "excluded_directory" if name in _EXCLUDED_DIRS else "symlink"})
                continue
            kept.append(name)
        directories[:] = kept
        for name in files:
            if name not in _ALLOWED:
                continue
            candidate = Path(current) / name
            if candidate.is_symlink():
                _fail()
            if not _config_in_scope(root, candidate):
                coverage["config_files_skipped_out_of_scope"] += 1
                continue
            count += 1
            if count > _MAX_FILES:
                _fail()
            try:
                relative = candidate.resolve(strict=True).relative_to(root).as_posix()
            except (OSError, ValueError):
                _fail()
            content = _read(candidate)
            if name == "application.properties": records.extend(_properties(content, relative))
            elif name in {"application.yml", "application.yaml"}: records.extend(_yaml(content, relative))
            else: records.extend(_webxml(content, relative))
    # duplicate known keys across files are ambiguous unless explicitly overridden.
    by_key: dict[str, list[ModeledConfigurationFact]] = {}
    for item in records: by_key.setdefault(item.key, []).append(item)
    output: list[ModeledConfigurationFact] = []
    for key, values in sorted(by_key.items()):
        known = [x for x in values if x.status == "known"]
        output.append(known[0] if len(values) == 1 and len(known) == 1 else _unknown(key, "", 0))
    for key, value in sorted((overrides or {}).items()):
        if not modeled_key_allowed(key):
            _fail()
        normalized = normalize_modeled_value(key, value)
        if normalized is None:
            _fail()
        output = [item for item in output if item.key != key]
        output.append(ModeledConfigurationFact(key, normalized, "", 0, "default", "cli_override", True, "known"))
    coverage["visited_entries"] = visited
    coverage["pruned_directory_entries"] = pruned
    coverage["config_files_read"] = count
    coverage["truncated"] = sample_truncated
    return [item.to_dict() for item in sorted(output, key=lambda x: str(x.config_id))]


def extract_modeled_configuration_with_coverage(
    source_root: Path,
    overrides: Mapping[str, str | int | bool] | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Extract finite modeled defaults and publish an auditable traversal-coverage snapshot."""
    coverage = _new_configuration_coverage()
    records = _extract_modeled_configuration(source_root, overrides, coverage)
    return records, coverage


def extract_modeled_configuration(
    source_root: Path,
    overrides: Mapping[str, str | int | bool] | None = None,
) -> list[dict[str, object]]:
    """Extract finite defaults only; symlinks, duplicate keys and uncertain profiles stay unknown."""
    records, _ = extract_modeled_configuration_with_coverage(source_root, overrides)
    return records
