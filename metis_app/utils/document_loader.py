"""metis_app.utils.document_loader — Format-aware document text extraction.

Uses kreuzberg (75+ formats: PDF, Office, OCR images, email, …) when the
package is installed, and falls back gracefully to plain UTF-8 reading for
``.txt`` / ``.md`` files when it is not.

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
import pathlib

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
# Public API
# ---------------------------------------------------------------------------


def is_kreuzberg_available() -> bool:
    """Return ``True`` if kreuzberg is installed and importable."""
    return _KREUZBERG_AVAILABLE


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


def load_document(
    path: str | pathlib.Path,
    *,
    use_kreuzberg: bool = True,
) -> str:
    """Extract text from *path* using the best available method.

    Parameters
    ----------
    path:
        Path to the document file.
    use_kreuzberg:
        If ``True`` (default) and kreuzberg is installed, delegate extraction
        to kreuzberg.  Set to ``False`` to force plain-text reading regardless.

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
