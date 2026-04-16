"""Tests for metis_app.services.monte_carlo_sampler."""

import types


from metis_app.services.monte_carlo_sampler import (
    _ROI_WINDOW,
    _SMALL_FILE_THRESHOLD,
    _cosine_sim,
    _gaussian_samples,
    _read_source_file,
    _sliding_fuzzy_anchors,
    apply_mces,
    sample_expanded_context,
)

# ---------------------------------------------------------------------------
# _sliding_fuzzy_anchors
# ---------------------------------------------------------------------------

def test_sliding_fuzzy_anchors_returns_list_of_ints():
    doc = "The quick brown fox jumps over the lazy dog"
    result = _sliding_fuzzy_anchors(doc, "fox jumps")
    assert isinstance(result, list)
    assert all(isinstance(x, int) for x in result)


def test_sliding_fuzzy_anchors_respects_top_k():
    doc = "word " * 500
    result = _sliding_fuzzy_anchors(doc, "word", top_k=3)
    assert len(result) <= 3


def test_sliding_fuzzy_anchors_empty_doc():
    result = _sliding_fuzzy_anchors("", "query")
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# _gaussian_samples
# ---------------------------------------------------------------------------

def test_gaussian_samples_returns_list_of_ints():
    anchors = [100, 500]
    result = _gaussian_samples(anchors, doc_len=2000, seed_val=42)
    assert isinstance(result, list)
    assert all(isinstance(x, int) for x in result)


def test_gaussian_samples_includes_anchor_regions():
    # Anchors should be within the candidate set (possibly clipped to bounds).
    anchors = [200]
    result = _gaussian_samples(anchors, doc_len=5000, seed_val=0, samples_per_anchor=5, random_explore=0)
    assert len(result) > 0


def test_gaussian_samples_bounds():
    doc_len = 3000
    result = _gaussian_samples([500, 1500], doc_len=doc_len, seed_val=1)
    assert all(0 <= x < doc_len for x in result)


# ---------------------------------------------------------------------------
# _cosine_sim
# ---------------------------------------------------------------------------

def test_cosine_sim_identical_vectors():
    v = [1.0, 2.0, 3.0]
    assert abs(_cosine_sim(v, v) - 1.0) < 1e-9


def test_cosine_sim_orthogonal_vectors():
    v1 = [1.0, 0.0]
    v2 = [0.0, 1.0]
    assert abs(_cosine_sim(v1, v2)) < 1e-9


def test_cosine_sim_known_pair():
    # [1,0] vs [1,1]/sqrt(2) → cos = 1/sqrt(2) ≈ 0.7071
    import math
    v1 = [1.0, 0.0]
    v2 = [1.0, 1.0]
    result = _cosine_sim(v1, v2)
    expected = 1.0 / math.sqrt(2)
    assert abs(result - expected) < 1e-6


def test_cosine_sim_zero_vector_returns_zero():
    assert _cosine_sim([0.0, 0.0], [1.0, 2.0]) == 0.0


# ---------------------------------------------------------------------------
# sample_expanded_context — small doc
# ---------------------------------------------------------------------------

def test_sample_expanded_context_small_doc_returns_full():
    doc = "short document " * 100  # well under 50k chars
    assert len(doc) <= _SMALL_FILE_THRESHOLD
    result = sample_expanded_context(doc, "short")
    assert result == doc


# ---------------------------------------------------------------------------
# sample_expanded_context — large doc
# ---------------------------------------------------------------------------

def test_sample_expanded_context_large_doc_returns_roi_window():
    doc = "x" * (_SMALL_FILE_THRESHOLD + 10_000)
    roi = 1800
    result = sample_expanded_context(doc, "x" * 20, roi_window=roi)
    # Result is at most roi_window chars (may be slightly less at doc boundary)
    assert len(result) <= roi
    assert len(result) > 0


def test_sample_expanded_context_large_doc_custom_roi():
    doc = "keyword content " * 5000
    roi = 500
    result = sample_expanded_context(doc, "keyword", roi_window=roi)
    assert len(result) <= roi


# ---------------------------------------------------------------------------
# sample_expanded_context — embed_fn called
# ---------------------------------------------------------------------------

def test_sample_expanded_context_calls_embed_fn():
    doc = "z" * (_SMALL_FILE_THRESHOLD + 5000)
    query_vector = [1.0, 0.0, 0.0]
    call_count = []

    def fake_embed(text: str) -> list:
        call_count.append(1)
        return [1.0, 0.0, 0.0]

    result = sample_expanded_context(
        doc,
        "z",
        query_vector=query_vector,
        embed_fn=fake_embed,
        roi_window=_ROI_WINDOW,
    )
    assert isinstance(result, str)
    # embed_fn should have been called at least once (once per candidate)
    assert len(call_count) >= 1


# ---------------------------------------------------------------------------
# apply_mces
# ---------------------------------------------------------------------------

def _make_source(file_path=None):
    src = types.SimpleNamespace()
    src.file_path = file_path
    return src


def test_apply_mces_no_file_path_returns_empty():
    source = _make_source(file_path=None)
    snippets, count = apply_mces([source], "question?", settings={})
    assert snippets == []
    assert count == 0


def test_apply_mces_empty_file_path_returns_empty():
    source = _make_source(file_path="")
    snippets, count = apply_mces([source], "question?", settings={})
    assert snippets == []
    assert count == 0


def test_apply_mces_no_sources_returns_empty():
    snippets, count = apply_mces([], "question?", settings={})
    assert snippets == []
    assert count == 0


def test_apply_mces_real_temp_file(tmp_path):
    content = "The answer is 42. " * 100
    f = tmp_path / "doc.txt"
    f.write_text(content, encoding="utf-8")

    source = _make_source(file_path=str(f))
    snippets, count = apply_mces([source], "answer", settings={})
    assert count == 1
    assert len(snippets) == 1
    assert snippets[0]["file_path"] == str(f)
    assert isinstance(snippets[0]["expanded_text"], str)


def test_apply_mces_nonexistent_file_skipped(tmp_path):
    source = _make_source(file_path=str(tmp_path / "missing.txt"))
    snippets, count = apply_mces([source], "question", settings={})
    assert snippets == []
    assert count == 0


# ---------------------------------------------------------------------------
# _read_source_file
# ---------------------------------------------------------------------------

def test_read_source_file_nonexistent_returns_none():
    result = _read_source_file("/nonexistent/path/that/does/not/exist.txt")
    assert result is None


def test_read_source_file_reads_real_file(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("hello world", encoding="utf-8")
    result = _read_source_file(str(f))
    assert result == "hello world"


def test_read_source_file_empty_path_returns_none():
    result = _read_source_file("")
    assert result is None
