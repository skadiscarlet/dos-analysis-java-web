from collections.abc import Mapping
from typing import Any


_EXIT_STATUS_BY_PREFIX = {
    "CONFIG_": 2,
    "CODEQL_": 3,
    "LLM_": 4,
    "ARTIFACT_": 5,
    "TOP50_": 5,
    "BATCH_": 5,
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
