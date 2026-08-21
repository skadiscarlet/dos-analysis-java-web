from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, cast

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.errors import AnalyzerError

_MAX_TEXT = 1024
_MAX_PATH = 512


def _invalid() -> None:
    raise AnalyzerError("ARTIFACT_SCHEMA_MISMATCH", "Modeled configuration fact is invalid.")


def _text(value: object, limit: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or len(value.encode("utf-8")) > limit:
        _invalid()
    return value


@dataclass(frozen=True)
class ModeledConfigurationFact:
    key: str
    value: str | int | bool | None
    source_file: str
    source_line: int
    profile: str
    provenance: Literal["cli_override", "config_file", "extracted_default", "unknown"]
    default_effective: bool
    status: Literal["known", "unknown"]
    config_id: str = ""

    def __post_init__(self) -> None:
        _text(self.key)
        if not isinstance(self.value, (str, int, bool, type(None))) or isinstance(self.value, float):
            _invalid()
        if isinstance(self.value, str) and ("\x00" in self.value or len(self.value.encode()) > _MAX_TEXT):
            _invalid()
        if not isinstance(self.source_file, str) or self.source_file.startswith("/") or ".." in self.source_file.split("/") or len(self.source_file.encode()) > _MAX_PATH:
            _invalid()
        if not isinstance(self.source_line, int) or isinstance(self.source_line, bool) or self.source_line < 0:
            _invalid()
        if self.profile not in {"default", "unknown"} or self.provenance not in {"cli_override", "config_file", "extracted_default", "unknown"} or self.status not in {"known", "unknown"} or not isinstance(self.default_effective, bool):
            _invalid()
        if self.status == "known" and (self.value is None or not self.default_effective):
            _invalid()
        if self.status == "unknown" and self.value is not None:
            _invalid()
        expected = stable_identifier("config", self.semantic_identity())
        if self.config_id and self.config_id != expected:
            _invalid()
        object.__setattr__(self, "config_id", expected)

    def semantic_identity(self) -> dict[str, object]:
        return {"key": self.key, "value": self.value, "source_file": self.source_file, "source_line": self.source_line, "profile": self.profile, "provenance": self.provenance, "default_effective": self.default_effective, "status": self.status}

    def to_dict(self) -> dict[str, object]:
        return {"config_id": self.config_id, **self.semantic_identity()}

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "ModeledConfigurationFact":
        if set(raw) != {"config_id", "key", "value", "source_file", "source_line", "profile", "provenance", "default_effective", "status"}:
            _invalid()
        return cls(cast(str, raw["key"]), cast(str | int | bool | None, raw["value"]), cast(str, raw["source_file"]), cast(int, raw["source_line"]), cast(str, raw["profile"]), cast(Literal["cli_override", "config_file", "extracted_default", "unknown"], raw["provenance"]), cast(bool, raw["default_effective"]), cast(Literal["known", "unknown"], raw["status"]), cast(str, raw["config_id"]))
