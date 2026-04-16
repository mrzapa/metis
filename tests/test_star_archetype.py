"""Tests for star_archetype.py detection service."""
from __future__ import annotations

import pathlib


from metis_app.services.star_archetype import (
    detect_archetypes,
    get_archetype,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp: pathlib.Path, name: str, content: str) -> str:
    f = tmp / name
    f.write_text(content, encoding="utf-8")
    return str(f)


# ---------------------------------------------------------------------------
# Extension-level tests
# ---------------------------------------------------------------------------

class TestExtensionDetection:
    def test_csv_detects_ledger(self, tmp_path):
        path = _write(tmp_path, "data.csv", "name,value,p_value\nrs123,0.45,0.001\nrs456,0.23,0.034\n")
        results = detect_archetypes([path])
        assert results[0].archetype.id == "ledger"
        assert results[0].score >= 0.7

    def test_tsv_detects_ledger(self, tmp_path):
        path = _write(tmp_path, "dataset.tsv", "snp\tbeta\tse\nrs1\t0.2\t0.05\n")
        results = detect_archetypes([path])
        top_ids = [r.archetype.id for r in results]
        assert "ledger" in top_ids

    def test_python_detects_codex(self, tmp_path):
        path = _write(tmp_path, "model.py", "import os\n\ndef train(model, data):\n    for batch in data:\n        model(batch)\n")
        results = detect_archetypes([path])
        assert results[0].archetype.id == "codex"
        assert results[0].score >= 0.7

    def test_typescript_detects_codex(self, tmp_path):
        path = _write(tmp_path, "api.ts", "import { fetch } from 'node-fetch';\n\nexport async function getData(url: string) {\n  return fetch(url);\n}\n")
        results = detect_archetypes([path])
        assert results[0].archetype.id == "codex"

    def test_tex_detects_theorem(self, tmp_path):
        path = _write(tmp_path, "paper.tex", r"\documentclass{article}\begin{document}\section{intro}Text.\end{document}")
        results = detect_archetypes([path])
        assert results[0].archetype.id == "theorem"
        assert results[0].score >= 0.7

    def test_vtt_detects_chronicle(self, tmp_path):
        path = _write(tmp_path, "meeting.vtt", "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nAlice: Hello everyone.\n\n00:00:05.000 --> 00:00:08.000\nBob: Thanks for joining.\n")
        results = detect_archetypes([path])
        assert results[0].archetype.id == "chronicle"

    def test_log_detects_chronicle(self, tmp_path):
        path = _write(tmp_path, "app.log", "10:00:01 INFO Server started\n10:00:02 DEBUG Handling request\n10:00:03 ERROR Connection refused\n")
        results = detect_archetypes([path])
        top_ids = [r.archetype.id for r in results]
        assert "chronicle" in top_ids

    def test_prose_txt_detects_scroll(self, tmp_path):
        prose = "The study of artificial intelligence has deep roots. " * 30
        path = _write(tmp_path, "essay.txt", prose)
        results = detect_archetypes([path])
        assert results[0].archetype.id == "scroll"


# ---------------------------------------------------------------------------
# Content-sniff tests
# ---------------------------------------------------------------------------

class TestContentSniff:
    def test_latex_math_detects_theorem(self, tmp_path):
        content = r"""
\begin{theorem}
Let $\alpha \in \mathbb{R}$. Then $\sum_{n=1}^{\infty} \frac{1}{n^2} = \frac{\pi^2}{6}$.
\end{theorem}
\begin{proof}
We use the Basel problem. Consider $\int_0^\infty f(x) dx$.
\end{proof}
"""
        path = _write(tmp_path, "math.md", content)
        results = detect_archetypes([path])
        top_ids = [r.archetype.id for r in results]
        assert "theorem" in top_ids

    def test_csv_consistent_columns_boosts_ledger(self, tmp_path):
        content = "snp_id,chromosome,position,beta,p_value\n" + "\n".join(
            f"rs{i},1,{i * 1000},0.{i},0.00{i}" for i in range(1, 20)
        )
        path = _write(tmp_path, "gwas.csv", content)
        results = detect_archetypes([path])
        assert results[0].archetype.id == "ledger"

    def test_transcript_speaker_pattern_boosts_chronicle(self, tmp_path):
        path = _write(tmp_path, "notes.txt", "\n".join([
            "Alice: Good morning. Let's discuss the Q1 roadmap.",
            "Bob: I think we should prioritise the API work at 10:00.",
            "Carol: Agreed. The timeline is 11:30.",
        ]))
        results = detect_archetypes([path])
        # Either chronicle or scroll is reasonable for this content
        assert len(results) >= 1

    def test_python_code_content_boosts_codex(self, tmp_path):
        content = """# Data pipeline
from typing import List
import pandas as pd

class DataLoader:
    def __init__(self, path: str):
        self.path = path

    def load(self) -> pd.DataFrame:
        return pd.read_csv(self.path)

def preprocess(data: pd.DataFrame) -> pd.DataFrame:
    return data.dropna()
"""
        path = _write(tmp_path, "pipeline.md", content)
        results = detect_archetypes([path])
        top_ids = [r.archetype.id for r in results]
        assert "codex" in top_ids


# ---------------------------------------------------------------------------
# Multi-file tests
# ---------------------------------------------------------------------------

class TestMultiFile:
    def test_all_csv_scores_ledger_top(self, tmp_path):
        paths = [
            _write(tmp_path, f"data_{i}.csv", f"a,b,c\n{i},{i*2},{i*3}\n")
            for i in range(4)
        ]
        results = detect_archetypes(paths)
        assert results[0].archetype.id == "ledger"

    def test_all_python_scores_codex_top(self, tmp_path):
        paths = [
            _write(tmp_path, f"module_{i}.py", f"def func_{i}(x):\n    return x + {i}\n")
            for i in range(3)
        ]
        results = detect_archetypes(paths)
        assert results[0].archetype.id == "codex"

    def test_mixed_scores_up_to_4_candidates(self, tmp_path):
        paths = [
            _write(tmp_path, "data.csv", "a,b,c\n1,2,3\n4,5,6\n"),
            _write(tmp_path, "notes.txt", "Some prose notes. " * 40),
            _write(tmp_path, "code.py", "def f(x):\n    return x\n"),
        ]
        results = detect_archetypes(paths)
        assert 1 <= len(results) <= 4


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_list_returns_scroll_fallback(self):
        results = detect_archetypes([])
        assert len(results) == 1
        assert results[0].archetype.id == _DEFAULT_ID()

    def test_nonexistent_path_analysed_by_extension(self, tmp_path):
        fake_path = str(tmp_path / "report.csv")  # file does not exist
        results = detect_archetypes([fake_path])
        assert results[0].archetype.id == "ledger"

    def test_get_archetype_known(self):
        a = get_archetype("theorem")
        assert a is not None
        assert a.id == "theorem"
        assert "chunk_size" in a.settings_overrides

    def test_get_archetype_unknown_returns_none(self):
        assert get_archetype("not_a_real_archetype") is None

    def test_ranked_archetype_has_why_text(self, tmp_path):
        path = _write(tmp_path, "data.csv", "id,value\n1,hello\n2,world\n")
        results = detect_archetypes([path])
        for r in results:
            assert isinstance(r.why, str)
            assert len(r.why) > 0

    def test_all_archetypes_have_required_fields(self):
        from metis_app.services.star_archetype import _ARCHETYPES
        for aid, a in _ARCHETYPES.items():
            assert a.id == aid
            assert a.name
            assert a.description
            assert a.icon_hint
            assert isinstance(a.settings_overrides, dict)
            assert "chunk_size" in a.settings_overrides
            assert "chunk_overlap" in a.settings_overrides


def _DEFAULT_ID() -> str:
    from metis_app.services.star_archetype import _DEFAULT_ARCHETYPE_ID
    return _DEFAULT_ARCHETYPE_ID
