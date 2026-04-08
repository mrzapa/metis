"""metis_app.utils.document_loader — Format-aware document text extraction.

Uses kreuzberg (75+ formats: PDF, Office, OCR images, email, …) when the
package is installed, and falls back gracefully to plain UTF-8 reading for
``.txt`` / ``.md`` files when it is not.

opendataloader-pdf (``document_loader = "opendataloader"`` in settings.json)
is the highest-accuracy option for PDF-heavy workloads.  It is bundled with
METIS via the ``jdk4py`` package — no separate Java installation is required.

Usage
-----
::

    from metis_app.utils.document_loader import load_document, is_kreuzberg_available

    text = load_document("/path/to/file.pdf")

Settings
--------
The caller may pass ``use_kreuzberg=False`` to force plain-text mode even
when kreuzberg is installed (e.g. when the user sets
``document_loader = "plain"`` in ``settings.json``).
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
import tempfile

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional kreuzberg import
# ---------------------------------------------------------------------------

try:
    from kreuzberg import extract_file_sync  # type: ignore[import]

    _KREUZBERG_AVAILABLE = True
    _log.debug("kreuzberg available — multi-format document extraction enabled")
except ImportError:
    _KREUZBERG_AVAILABLE = False
    _log.debug(
        "kreuzberg not installed — install with: pip install 'metis-app[kreuzberg]'"
    )

# ---------------------------------------------------------------------------
# jdk4py — bundled JDK so opendataloader-pdf needs no system Java
# ---------------------------------------------------------------------------

try:
    import jdk4py as _jdk4py  # type: ignore[import]

    if not os.environ.get("JAVA_HOME"):
        os.environ["JAVA_HOME"] = str(_jdk4py.JAVA_HOME)
    _java_bin = str(_jdk4py.JAVA_HOME / "bin")
    if _java_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _java_bin + os.pathsep + os.environ.get("PATH", "")
    _log.debug("jdk4py: using bundled JDK at %s", _jdk4py.JAVA_HOME)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Optional opendataloader-pdf import
# ---------------------------------------------------------------------------

try:
    import opendataloader_pdf as _odl  # type: ignore[import]

    _OPENDATALOADER_AVAILABLE = True
    _log.debug("opendataloader-pdf available — high-accuracy PDF extraction enabled")
except ImportError:
    _odl = None  # type: ignore[assignment]
    _OPENDATALOADER_AVAILABLE = False
    _log.debug(
        "opendataloader-pdf not installed — install with: pip install 'metis-app[opendataloader]'"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_kreuzberg_available() -> bool:
    """Return ``True`` if kreuzberg is installed and importable."""
    return _KREUZBERG_AVAILABLE


def is_opendataloader_available() -> bool:
    """Return ``True`` if opendataloader-pdf is installed and importable."""
    return _OPENDATALOADER_AVAILABLE


# File extensions that kreuzberg handles well beyond plain text.
# Used by the file-open dialog to show useful filter groups.
KREUZBERG_EXTENSIONS: dict[str, list[str]] = {
    "PDF":        ["*.pdf"],
    "Word":       ["*.docx", "*.doc"],
    "Excel":      ["*.xlsx", "*.xls"],
    "PowerPoint": ["*.pptx", "*.ppt"],
    "Images":     ["*.png", "*.jpg", "*.jpeg", "*.tiff", "*.tif", "*.bmp", "*.webp"],
    "Email":      ["*.eml", "*.msg"],
    "Web":        ["*.html", "*.htm"],
    "eBook":      ["*.epub"],
}


def batch_extract_pdfs(paths: list[str | pathlib.Path]) -> dict[str, str]:
    """Batch-extract PDFs with opendataloader-pdf using a single JVM startup.

    Parameters
    ----------
    paths:
        List of PDF file paths to extract.

    Returns
    -------
    dict[str, str]
        Mapping of ``str(original_path)`` → extracted Markdown text.
        Paths that failed extraction are omitted (callers should fall back).
    """
    if not _OPENDATALOADER_AVAILABLE or not paths:
        return {}

    result: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = pathlib.Path(tmpdir)
        # Use separate in/out subdirs — input files are copied with an index
        # prefix (e.g. "0_report.pdf") so two PDFs with the same stem never
        # collide in the output directory while still using a single JVM call.
        in_dir = tmpdir_path / "in"
        out_dir = tmpdir_path / "out"
        in_dir.mkdir()
        out_dir.mkdir()

        staging: list[tuple[pathlib.Path, pathlib.Path]] = []  # (staged, original)
        for idx, p in enumerate(paths):
            p = pathlib.Path(p)
            staged = in_dir / f"{idx}_{p.name}"
            shutil.copy2(str(p), str(staged))
            staging.append((staged, p))

        try:
            _odl.convert(
                input_path=[str(s) for s, _ in staging],
                output_dir=str(out_dir),
                format="markdown",
            )
        except Exception as exc:
            _log.warning("opendataloader-pdf batch conversion failed (%s) — skipping", exc)
            return result

        for staged, orig in staging:
            # opendataloader-pdf writes <stem>.md for each input file
            md_path = out_dir / (staged.stem + ".md")
            if md_path.exists():
                text = md_path.read_text(encoding="utf-8", errors="replace")
                _log.debug(
                    "opendataloader-pdf extracted %d chars from '%s'",
                    len(text),
                    orig.name,
                )
                result[str(orig)] = text
            else:
                _log.warning(
                    "opendataloader-pdf produced no output for '%s'", orig.name
                )

    return result


def load_document(
    path: str | pathlib.Path,
    *,
    use_kreuzberg: bool = True,
    use_opendataloader: bool = False,
) -> str:
    """Extract text from *path* using the best available method.

    Parameters
    ----------
    path:
        Path to the document file.
    use_kreuzberg:
        If ``True`` (default) and kreuzberg is installed, delegate extraction
        to kreuzberg.  Set to ``False`` to force plain-text reading regardless.
    use_opendataloader:
        If ``True`` and opendataloader-pdf is installed, use it for ``.pdf``
        files (single-file mode — one JVM startup per call).  For bulk PDF
        indexing prefer :func:`batch_extract_pdfs` to amortise JVM startup.

    Returns
    -------
    str
        Extracted text content.

    Raises
    ------
    OSError
        If the file cannot be opened (plain-text path).
    """
    path = pathlib.Path(path)

    if use_opendataloader and _OPENDATALOADER_AVAILABLE and path.suffix.lower() == ".pdf":
        extracted = batch_extract_pdfs([path])
        if str(path) in extracted:
            return extracted[str(path)]
        _log.warning(
            "opendataloader-pdf failed for '%s' — falling through to kreuzberg/plain",
            path.name,
        )

    if use_kreuzberg and _KREUZBERG_AVAILABLE:
        try:
            result = extract_file_sync(path)
            _log.debug(
                "kreuzberg extracted %d chars from '%s'",
                len(result.content),
                path.name,
            )
            return result.content
        except Exception as exc:  # KreuzbergError or any unexpected error
            _log.warning(
                "kreuzberg could not extract '%s' (%s) — falling back to plain text",
                path.name,
                exc,
            )

    # Plain-text fallback — always works for .txt / .md; may produce garbled
    # output for binary formats, but that's acceptable as a last resort.
    _log.debug("Plain-text read: '%s'", path.name)
    return path.read_text(encoding="utf-8", errors="replace")
