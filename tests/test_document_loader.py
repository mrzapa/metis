"""tests/test_document_loader.py — Unit tests for the document_loader utility.

Tests are written to pass whether or not kreuzberg is installed:
- ``is_kreuzberg_available()`` is always callable and returns a bool.
- ``load_document()`` with ``use_kreuzberg=False`` always uses plain-text
  reading, so those tests have no kreuzberg dependency.
- kreuzberg-specific behaviour is verified only when it is importable.
"""

from __future__ import annotations

import pathlib

import pytest

from axiom_app.utils.document_loader import (
    KREUZBERG_EXTENSIONS,
    is_kreuzberg_available,
    load_document,
)


# ---------------------------------------------------------------------------
# is_kreuzberg_available
# ---------------------------------------------------------------------------


class TestIsKreuzbergAvailable:
    def test_returns_bool(self):
        assert isinstance(is_kreuzberg_available(), bool)


# ---------------------------------------------------------------------------
# KREUZBERG_EXTENSIONS
# ---------------------------------------------------------------------------


class TestKreuzbergExtensions:
    def test_is_dict(self):
        assert isinstance(KREUZBERG_EXTENSIONS, dict)

    def test_pdf_included(self):
        assert "PDF" in KREUZBERG_EXTENSIONS
        assert "*.pdf" in KREUZBERG_EXTENSIONS["PDF"]

    def test_all_values_are_lists_of_strings(self):
        for label, exts in KREUZBERG_EXTENSIONS.items():
            assert isinstance(exts, list), f"{label!r} value should be a list"
            for ext in exts:
                assert isinstance(ext, str), f"{label!r} extension {ext!r} should be str"
                assert ext.startswith("*."), f"Extension {ext!r} should start with '*.' "


# ---------------------------------------------------------------------------
# load_document — plain-text fallback (always available)
# ---------------------------------------------------------------------------


class TestLoadDocumentPlainText:
    def test_reads_txt_file(self, tmp_path: pathlib.Path):
        f = tmp_path / "sample.txt"
        f.write_text("Hello, Axiom!", encoding="utf-8")
        result = load_document(f, use_kreuzberg=False)
        assert result == "Hello, Axiom!"

    def test_reads_md_file(self, tmp_path: pathlib.Path):
        f = tmp_path / "notes.md"
        f.write_text("# Title\n\nSome content.", encoding="utf-8")
        result = load_document(f, use_kreuzberg=False)
        assert "Title" in result
        assert "Some content." in result

    def test_accepts_string_path(self, tmp_path: pathlib.Path):
        f = tmp_path / "str_path.txt"
        f.write_text("via string path", encoding="utf-8")
        result = load_document(str(f), use_kreuzberg=False)
        assert result == "via string path"

    def test_missing_file_raises_oserror(self, tmp_path: pathlib.Path):
        missing = tmp_path / "does_not_exist.txt"
        with pytest.raises(OSError):
            load_document(missing, use_kreuzberg=False)

    def test_empty_file_returns_empty_string(self, tmp_path: pathlib.Path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        result = load_document(f, use_kreuzberg=False)
        assert result == ""

    def test_unicode_content_preserved(self, tmp_path: pathlib.Path):
        content = "日本語テスト 🎉 Ünïcödé"
        f = tmp_path / "unicode.txt"
        f.write_text(content, encoding="utf-8")
        result = load_document(f, use_kreuzberg=False)
        assert result == content


# ---------------------------------------------------------------------------
# load_document — kreuzberg path (skipped when not installed)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not is_kreuzberg_available(),
    reason="kreuzberg not installed",
)
class TestLoadDocumentKreuzberg:
    def test_falls_back_on_plain_txt(self, tmp_path: pathlib.Path):
        """kreuzberg should still handle plain text without error."""
        f = tmp_path / "plain.txt"
        f.write_text("kreuzberg plain text test", encoding="utf-8")
        result = load_document(f, use_kreuzberg=True)
        assert "kreuzberg plain text test" in result

    def test_use_kreuzberg_true_does_not_raise_on_txt(self, tmp_path: pathlib.Path):
        f = tmp_path / "ok.txt"
        f.write_text("content", encoding="utf-8")
        # Should not raise — either succeeds via kreuzberg or falls back.
        result = load_document(f, use_kreuzberg=True)
        assert isinstance(result, str)
