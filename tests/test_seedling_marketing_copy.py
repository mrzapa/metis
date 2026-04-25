"""Marketing-copy guard for the M13 Seedling pitch.

ADR 0013 §3 forbids unqualified ``"reflects while you sleep"`` (or
similar absolute claims) anywhere in the user-facing frontend.
Bonsai-driven reflection only runs while the dock is open; the
"morning-after" promise from VISION.md is gated on backend GGUF
opt-in. Until that opt-in ships in Phase 4b, the promise must not
appear in the UI without an explicit qualifier.

This test fails CI if a forbidden phrase appears anywhere under
``apps/metis-web/`` without a sibling qualifier on the same line. The
intent is mechanical: a future copy reviewer cannot accidentally land
the wrong promise without the test going red.
"""

from __future__ import annotations

import pathlib

# Phrases that overpromise overnight reflection. Add new variants as
# they show up in copy review.
_FORBIDDEN: tuple[str, ...] = (
    "reflects while you sleep",
    "reflect while you sleep",
    "thinks while you sleep",
    "learns while you sleep",
    "while you sleep,",
    "while you sleep.",
)

# Tokens that, when present on the same line, mark the claim as
# qualified — usually because the copy is talking about the opt-in
# backend path or is itself a guard string.
_QUALIFIERS: tuple[str, ...] = (
    "configure",
    "optional",
    "opt-in",
    "opt in",
    "backend gguf",
    "if you've",
    "when you've",
    "requires",
    "_qualified",
    "forbidden",
    "test_seedling_marketing_copy",
    "no qualifier",
    "@allow-marketing-copy",
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_FRONTEND_ROOT = _REPO_ROOT / "apps" / "metis-web"

# Skip noise that is not user-facing copy.
_SKIP_DIRS: frozenset[str] = frozenset(
    {".next", "node_modules", "dist", "out", "coverage", "playwright-report"}
)
_INCLUDE_SUFFIXES: frozenset[str] = frozenset({".tsx", ".ts", ".md", ".mdx", ".json"})


def _iter_copy_files() -> list[pathlib.Path]:
    if not _FRONTEND_ROOT.exists():
        return []
    files: list[pathlib.Path] = []
    for path in _FRONTEND_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in _INCLUDE_SUFFIXES:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def test_no_unqualified_overnight_reflection_promise() -> None:
    offenders: list[str] = []
    for path in _iter_copy_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, raw in enumerate(text.splitlines(), start=1):
            line = raw.lower()
            if not any(phrase in line for phrase in _FORBIDDEN):
                continue
            if any(qualifier in line for qualifier in _QUALIFIERS):
                continue
            rel = path.relative_to(_REPO_ROOT)
            offenders.append(f"{rel}:{line_no}: {raw.strip()}")

    assert not offenders, (
        "Unqualified overnight-reflection copy detected (ADR 0013 §3). "
        "Either rephrase to qualify the claim or add a 'no qualifier' "
        "comment on the same line if the string is intentionally a guard.\n"
        + "\n".join(offenders)
    )
