from __future__ import annotations

import os
import stat
from pathlib import Path
from collections.abc import Iterable

from dosweb.artifacts.identifiers import canonical_json
from dosweb.errors import AnalyzerError
from dosweb.reachability.models import LlmAuditRecord

_MAX_AUDIT_BYTES = 512 * 1024


def publish_private_audit(path: Path, records: Iterable[LlmAuditRecord]) -> None:
    """Atomically publish bounded provider audit records with 0600 permissions."""
    rows = [record.to_dict() for record in records]
    payload = b"".join(canonical_json(row) + b"\n" for row in rows)
    if len(payload) > _MAX_AUDIT_BYTES or b"Authorization" in payload or b"DEEPSEEK_API_KEY" in payload:
        raise AnalyzerError("LLM_AUDIT_INVALID", "LLM audit is oversized or contains authentication material.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, payload); os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        os.chmod(path, 0o600)
