"""GET /v1/logs/tail — safe, redacted log tail endpoint."""

from __future__ import annotations

import pathlib
import re
from typing import Any

from fastapi import APIRouter

import axiom_app.settings_store as _store

router = APIRouter()

_TAIL_LINES = 200
_LOG_FILENAME = "axiom.log"
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

# Redaction rules applied in order:
#   1. api_key_* assignments  (most specific — preserve key name)
#   2. Bearer tokens          (HTTP auth headers)
#   3. Long opaque tokens     (≥32 alphanum chars — conservative catch-all)
_REDACT: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(api_key_\w+\s*[=:]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(Bearer\s+)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"[A-Za-z0-9+/\-_]{32,}"), "[REDACTED]"),
]


def _redact(line: str) -> str:
    for pat, repl in _REDACT:
        line = pat.sub(repl, line)
    return line


@router.get("/v1/logs/tail")
def get_log_tail() -> dict[str, Any]:
    """Return the last 200 lines of axiom.log with secrets redacted.

    The log path is derived exclusively from the ``log_dir`` setting plus the
    hardcoded filename ``axiom.log`` — no user-controlled path segments are
    accepted, so arbitrary file reads are not possible.
    """
    settings = _store.load_settings()
    log_dir = pathlib.Path(settings.get("log_dir", "logs"))
    if not log_dir.is_absolute():
        log_dir = _REPO_ROOT / log_dir
    log_path = log_dir / _LOG_FILENAME

    if not log_path.exists():
        return {"lines": [], "missing": True, "log_path": str(log_path)}

    raw = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = [_redact(line) for line in raw[-_TAIL_LINES:]]
    return {
        "lines": tail,
        "missing": False,
        "log_path": str(log_path),
        "total_lines": len(raw),
    }
