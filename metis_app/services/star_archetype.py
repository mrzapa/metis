"""Star Archetype detection — recommends an indexing personality for uploaded content.

Each archetype is a named indexing strategy that tangibly differentiates stars:
  Scroll   → dense prose / long-form text
  Ledger   → tabular data / CSVs / datasets
  Codex    → source code / notebooks
  Chronicle→ transcripts / logs / meeting notes / emails (chronological)
  Signal   → image-rich PDFs / multimodal reports
  Dispatch → short-form: notes, emails, threads
  Theorem  → formal papers / math / LaTeX / academic
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class StarArchetype:
    id: str
    name: str
    description: str
    icon_hint: str  # lucide icon name for the frontend
    settings_overrides: dict[str, Any]


@dataclass(slots=True)
class RankedArchetype:
    archetype: StarArchetype
    score: float          # 0.0 – 1.0; highest first
    why: str              # human-readable rationale shown to user


# ---------------------------------------------------------------------------
# Archetype catalogue
# ---------------------------------------------------------------------------

_ARCHETYPES: dict[str, StarArchetype] = {
    "scroll": StarArchetype(
        id="scroll",
        name="Scroll",
        description="Dense prose — essays, reports, long articles, documentation.",
        icon_hint="book-open",
        settings_overrides={
            "chunk_size": 650,
            "chunk_overlap": 160,
            "retrieval_mode": "flat",
        },
    ),
    "ledger": StarArchetype(
        id="ledger",
        name="Ledger",
        description="Tabular datasets, CSV/TSV files, spreadsheets, structured records.",
        icon_hint="table",
        settings_overrides={
            "chunk_size": 160,
            "chunk_overlap": 16,
            "retrieval_mode": "flat",
            "build_digest_index": False,
            "build_comprehension_index": False,
        },
    ),
    "codex": StarArchetype(
        id="codex",
        name="Codex",
        description="Source code, Jupyter notebooks, configuration files.",
        icon_hint="code-2",
        settings_overrides={
            "chunk_size": 380,
            "chunk_overlap": 60,
            "retrieval_mode": "flat",
        },
    ),
    "chronicle": StarArchetype(
        id="chronicle",
        name="Chronicle",
        description="Transcripts, meeting notes, event logs, conversation threads.",
        icon_hint="clock",
        settings_overrides={
            "chunk_size": 320,
            "chunk_overlap": 80,
            "retrieval_mode": "hierarchical",
            "build_digest_index": True,
            "build_comprehension_index": False,
        },
    ),
    "signal": StarArchetype(
        id="signal",
        name="Signal",
        description="Reports with figures, charts, and mixed image+text content.",
        icon_hint="activity",
        settings_overrides={
            "chunk_size": 800,
            "chunk_overlap": 200,
            "retrieval_mode": "hierarchical",
            "build_digest_index": False,
            "build_comprehension_index": True,
        },
    ),
    "dispatch": StarArchetype(
        id="dispatch",
        name="Dispatch",
        description="Short-form content — emails, notes, messages, clippings.",
        icon_hint="message-square",
        settings_overrides={
            "chunk_size": 180,
            "chunk_overlap": 30,
            "retrieval_mode": "flat",
            "build_digest_index": False,
        },
    ),
    "theorem": StarArchetype(
        id="theorem",
        name="Theorem",
        description="Academic papers, mathematics, formal logic, LaTeX documents.",
        icon_hint="sigma",
        settings_overrides={
            "chunk_size": 820,
            "chunk_overlap": 210,
            "retrieval_mode": "hierarchical",
            "build_digest_index": True,
            "build_comprehension_index": True,
            "comprehension_extraction_depth": "Deep",
            "agentic_mode": True,
            "agentic_max_iterations": 3,
        },
    ),
}

# Default when nothing matches
_DEFAULT_ARCHETYPE_ID = "scroll"

# ---------------------------------------------------------------------------
# Extension maps
# ---------------------------------------------------------------------------

_LEDGER_EXTENSIONS = {".csv", ".tsv", ".parquet", ".arrow"}
_SPREADSHEET_EXTENSIONS = {".xls", ".xlsx", ".ods"}

_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".cxx",
    ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
    ".scala", ".lua", ".r", ".sql", ".sh", ".bash", ".zsh", ".ps1",
    ".ipynb", ".clj", ".ex", ".exs", ".hs", ".ml",
}

_TRANSCRIPT_EXTENSIONS = {".vtt", ".srt", ".sub"}
_EMAIL_EXTENSIONS = {".eml", ".msg"}
_LOG_EXTENSIONS = {".log"}

_ACADEMIC_EXTENSIONS = {".tex", ".bib", ".bibtex"}

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif"}

# ---------------------------------------------------------------------------
# Content sniffers
# ---------------------------------------------------------------------------

def _sniff(path: pathlib.Path, max_bytes: int = 4096) -> str:
    """Return the first `max_bytes` of a file as a string. Never raises."""
    try:
        with open(path, "r", encoding="latin-1", errors="replace") as fh:
            return fh.read(max_bytes)
    except (OSError, PermissionError, IsADirectoryError):
        return ""


_RE_CSV_HEADER = re.compile(r'^[^\n]{5,}\,[^\n]{3,}', re.MULTILINE)
_RE_TIMESTAMP = re.compile(r'\b\d{1,2}:\d{2}(?::\d{2})?\b')
_RE_SPEAKER = re.compile(r'^[A-Z][A-Za-z\s]{0,25}:\s', re.MULTILINE)
_RE_MATH = re.compile(r'\\(?:frac|int|sum|prod|alpha|beta|gamma|theta|lambda|sigma|mu|infty|partial|nabla|Rightarrow|Leftrightarrow|begin\{(?:equation|align|theorem|proof|lemma|corollary)\})|[∈∉∀∃∂∇∑∏∫≤≥≠≈∞]')
_RE_PYTHON_CODE = re.compile(r'\bdef \w+\(|class \w+[\(:]|import \w+|from \w+ import')
_RE_GENERIC_CODE = re.compile(r'(?:function\s+\w+\s*\(|public\s+(?:class|static|void|int|String)\s+|fn\s+\w+\s*\(|def\s+\w+\s*\(|sub\s+\w+\s*\()')


def _score_for_file(
    path: pathlib.Path,
    snippet: str,
) -> dict[str, float]:
    """Return a score per archetype ID for a single file."""
    ext = path.suffix.lower()
    scores: dict[str, float] = {aid: 0.0 for aid in _ARCHETYPES}

    # --- Ledger ---
    if ext in _LEDGER_EXTENSIONS:
        scores["ledger"] += 0.9
    elif ext in _SPREADSHEET_EXTENSIONS:
        scores["ledger"] += 0.7
    elif ext in {".csv", ".tsv"} or _RE_CSV_HEADER.search(snippet):
        scores["ledger"] += 0.8

    # CSV sniff: commas + consistent column count in first lines
    if snippet and _csv_column_consistency(snippet):
        scores["ledger"] += 0.2

    # --- Codex ---
    if ext in _CODE_EXTENSIONS:
        scores["codex"] += 0.9
    if snippet:
        py_matches = len(_RE_PYTHON_CODE.findall(snippet))
        gen_matches = len(_RE_GENERIC_CODE.findall(snippet))
        code_hits = py_matches + gen_matches
        if code_hits >= 3:
            scores["codex"] += 0.45
        elif code_hits >= 1:
            scores["codex"] += 0.2

    # --- Chronicle ---
    if ext in _TRANSCRIPT_EXTENSIONS:
        scores["chronicle"] += 0.95
    if ext in _EMAIL_EXTENSIONS:
        scores["chronicle"] += 0.6
        scores["dispatch"] += 0.3
    if ext in _LOG_EXTENSIONS:
        scores["chronicle"] += 0.7
    if snippet:
        ts_count = len(_RE_TIMESTAMP.findall(snippet))
        sp_count = len(_RE_SPEAKER.findall(snippet))
        if ts_count >= 3:
            scores["chronicle"] += min(0.4, ts_count * 0.08)
        if sp_count >= 2:
            scores["chronicle"] += min(0.3, sp_count * 0.06)

    # --- Theorem ---
    if ext in _ACADEMIC_EXTENSIONS:
        scores["theorem"] += 0.95
    if snippet:
        math_count = len(_RE_MATH.findall(snippet))
        if math_count >= 3:
            scores["theorem"] += min(0.45, math_count * 0.06)
        if "abstract" in snippet[:1200].lower() and "introduction" in snippet[:2000].lower():
            scores["theorem"] += 0.2
        if "\\begin{document}" in snippet or "\\documentclass" in snippet:
            scores["theorem"] += 0.5

    # --- Dispatch (short, plain text) ---
    if ext in _EMAIL_EXTENSIONS:
        scores["dispatch"] += 0.3
    if snippet:
        line_count = snippet.count("\n") + 1
        char_count = len(snippet)
        avg_line = char_count / max(1, line_count)
        if char_count < 1500 and avg_line < 60:
            scores["dispatch"] += 0.35
        elif char_count < 3000 and avg_line < 80:
            scores["dispatch"] += 0.15

    # --- Signal (PDF with figures / image files) ---
    if ext == ".pdf":
        # Will be boosted at the set level if image files co-present
        scores["signal"] += 0.1
    if ext in _IMAGE_EXTENSIONS:
        scores["signal"] += 0.4

    # --- Scroll (long-form prose) — default score ---
    if ext in {".txt", ".md", ".markdown", ".rst", ".html", ".htm", ".epub", ".pdf", ".docx", ".doc"}:
        if snippet:
            word_count = len(snippet.split())
            if word_count > 300:
                scores["scroll"] += 0.4
            elif word_count > 100:
                scores["scroll"] += 0.2
        else:
            scores["scroll"] += 0.15

    return scores


def _csv_column_consistency(snippet: str) -> bool:
    """True if the first 5 non-empty lines have roughly the same comma count (≥3)."""
    lines = [ln for ln in snippet.splitlines() if ln.strip()][:6]
    if len(lines) < 2:
        return False
    counts = [ln.count(",") for ln in lines]
    if counts[0] < 2:
        return False
    return max(counts) - min(counts) <= 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_archetypes(file_paths: list[str]) -> list[RankedArchetype]:
    """Analyse `file_paths` and return up to 4 ranked archetype candidates.

    Files are expected to already be accessible on the local filesystem
    (i.e. already uploaded).  Any path that cannot be read is analysed by
    extension alone.
    """
    if not file_paths:
        default = _ARCHETYPES[_DEFAULT_ARCHETYPE_ID]
        return [RankedArchetype(archetype=default, score=0.5, why="No files provided — using general-purpose prose indexing.")]

    # Accumulate scores across all files
    totals: dict[str, float] = {aid: 0.0 for aid in _ARCHETYPES}
    reasons: dict[str, list[str]] = {aid: [] for aid in _ARCHETYPES}

    ext_tally: dict[str, int] = {}
    has_images = False
    file_count = len(file_paths)

    for raw_path in file_paths:
        path = pathlib.Path(raw_path)
        ext = path.suffix.lower()
        ext_tally[ext] = ext_tally.get(ext, 0) + 1
        if ext in _IMAGE_EXTENSIONS:
            has_images = True
        snippet = _sniff(path)
        per_file = _score_for_file(path, snippet)
        for aid, s in per_file.items():
            totals[aid] += s

    # Boost Signal if image files appear alongside non-image files
    non_image_count = sum(
        v for k, v in ext_tally.items() if k not in _IMAGE_EXTENSIONS
    )
    if has_images and non_image_count > 0:
        totals["signal"] += 0.5 * non_image_count

    # Normalise to 0–1 against the number of files
    for aid in totals:
        totals[aid] = min(1.0, totals[aid] / file_count)

    # Build human-readable reasons per archetype
    dominant_exts = sorted(ext_tally, key=lambda e: -ext_tally[e])[:3]
    ext_summary = ", ".join(
        f"{ext_tally[e]} {e}" for e in dominant_exts if e
    ) or "unknown format"

    reasons["ledger"].append(f"Tabular format detected ({ext_summary})" if totals["ledger"] > 0.25 else "Structured row-based indexing")
    reasons["codex"].append(f"Source code detected ({ext_summary})" if totals["codex"] > 0.25 else "Code-optimised chunking")
    reasons["chronicle"].append("Chronological / transcript content detected" if totals["chronicle"] > 0.25 else "Temporal ordering support")
    reasons["theorem"].append("Academic / mathematical content detected" if totals["theorem"] > 0.25 else "Deep formal reasoning indexing")
    reasons["signal"].append(f"Mixed media or figures detected ({ext_summary})" if totals["signal"] > 0.25 else "Multimodal comprehension indexing")
    reasons["dispatch"].append(f"Short-form content detected ({ext_summary})" if totals["dispatch"] > 0.25 else "Granular short-text retrieval")
    reasons["scroll"].append(f"Long-form prose ({ext_summary})")

    # Filter archetypes with a non-trivial score and rank
    threshold = 0.05
    ranked = sorted(
        [
            RankedArchetype(
                archetype=_ARCHETYPES[aid],
                score=round(totals[aid], 3),
                why=" · ".join(reasons[aid]) or _ARCHETYPES[aid].description,
            )
            for aid in totals
            if totals[aid] >= threshold
        ],
        key=lambda r: -r.score,
    )[:4]

    # Always include at least the Scroll fallback
    if not ranked:
        default = _ARCHETYPES[_DEFAULT_ARCHETYPE_ID]
        ranked = [RankedArchetype(archetype=default, score=0.5, why=f"General-purpose prose indexing ({ext_summary}).")]

    # If top score is very high (≥0.7), trim the list to 2 so the UI is decisive
    if ranked[0].score >= 0.7:
        ranked = ranked[:2]

    return ranked


def get_archetype(archetype_id: str) -> StarArchetype | None:
    """Return an archetype by ID, or None if not found."""
    return _ARCHETYPES.get(archetype_id)
