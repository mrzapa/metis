"""Tests for metis_app.services.grep_retriever."""

import json
from unittest.mock import patch

import pytest

from metis_app.services.grep_retriever import (
    _parse_rga_stdout,
    extract_keywords,
    map_hits_to_chunks,
    rrf_fuse,
    run_rga,
)

# ---------------------------------------------------------------------------
# extract_keywords
# ---------------------------------------------------------------------------

def test_extract_keywords_omits_stopwords():
    result = extract_keywords("What is the capital of France?")
    lowered = [t.lower() for t in result]
    # Common stopwords should be absent
    for stopword in ("what", "is", "the", "of"):
        assert stopword not in lowered
    # Content words should be present
    assert "capital" in lowered
    assert "france" in lowered


def test_extract_keywords_empty_string_returns_empty():
    assert extract_keywords("") == []


def test_extract_keywords_respects_max_terms():
    long_query = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    result = extract_keywords(long_query, max_terms=3)
    assert len(result) <= 3


def test_extract_keywords_returns_list_of_strings():
    result = extract_keywords("machine learning neural network")
    assert isinstance(result, list)
    assert all(isinstance(t, str) for t in result)


# ---------------------------------------------------------------------------
# _parse_rga_stdout
# ---------------------------------------------------------------------------

def _make_match_line(file: str, line_number: int, text: str) -> str:
    obj = {
        "type": "match",
        "data": {
            "path": {"text": file},
            "line_number": line_number,
            "lines": {"text": text + "\n"},
        },
    }
    return json.dumps(obj)


def test_parse_rga_stdout_valid_match():
    line = _make_match_line("/data/file.txt", 42, "hello world")
    result = _parse_rga_stdout(line)
    assert len(result) == 1
    assert result[0]["file"] == "/data/file.txt"
    assert result[0]["line_number"] == 42
    assert result[0]["text"] == "hello world"


def test_parse_rga_stdout_empty_string():
    assert _parse_rga_stdout("") == []


def test_parse_rga_stdout_non_match_type_skipped():
    begin = json.dumps({"type": "begin", "data": {"path": {"text": "/f.txt"}}})
    end = json.dumps({"type": "end", "data": {}})
    stdout = "\n".join([begin, end])
    assert _parse_rga_stdout(stdout) == []


def test_parse_rga_stdout_multiple_matches():
    lines = [
        _make_match_line("/a.txt", 1, "first"),
        _make_match_line("/b.txt", 2, "second"),
    ]
    result = _parse_rga_stdout("\n".join(lines))
    assert len(result) == 2
    assert result[0]["file"] == "/a.txt"
    assert result[1]["file"] == "/b.txt"


def test_parse_rga_stdout_invalid_json_skipped():
    stdout = "not json\n" + _make_match_line("/ok.txt", 1, "valid")
    result = _parse_rga_stdout(stdout)
    assert len(result) == 1
    assert result[0]["file"] == "/ok.txt"


# ---------------------------------------------------------------------------
# map_hits_to_chunks
# ---------------------------------------------------------------------------

def test_map_hits_to_chunks_returns_correct_index():
    hits = [{"file": "/data/doc.txt", "line_number": 10, "text": "match"}]
    chunks = [
        {"file_path": "/other.txt", "start_line": 0},
        {"file_path": "/data/doc.txt", "start_line": 8},
    ]
    result = map_hits_to_chunks(hits, chunks)
    assert 1 in result


def test_map_hits_to_chunks_no_matching_file_returns_empty():
    hits = [{"file": "/nowhere.txt", "line_number": 5, "text": "x"}]
    chunks = [{"file_path": "/other.txt", "start_line": 0}]
    result = map_hits_to_chunks(hits, chunks)
    assert result == []


def test_map_hits_to_chunks_picks_closest_start_line():
    hits = [{"file": "/doc.txt", "line_number": 100, "text": "x"}]
    chunks = [
        {"file_path": "/doc.txt", "start_line": 10},   # far
        {"file_path": "/doc.txt", "start_line": 95},   # close
        {"file_path": "/doc.txt", "start_line": 200},  # farther
    ]
    result = map_hits_to_chunks(hits, chunks)
    # Chunk index 1 (start_line=95) is closest to line 100
    assert result[0] == 1


def test_map_hits_to_chunks_deduplicates_results():
    hits = [
        {"file": "/doc.txt", "line_number": 5, "text": "a"},
        {"file": "/doc.txt", "line_number": 6, "text": "b"},
    ]
    chunks = [{"file_path": "/doc.txt", "start_line": 5}]
    result = map_hits_to_chunks(hits, chunks)
    # Same chunk should appear only once
    assert len(result) == len(set(result))


def test_map_hits_to_chunks_empty_hits_returns_empty():
    chunks = [{"file_path": "/doc.txt", "start_line": 0}]
    assert map_hits_to_chunks([], chunks) == []


# ---------------------------------------------------------------------------
# rrf_fuse
# ---------------------------------------------------------------------------

def test_rrf_fuse_items_in_both_lists_rank_higher():
    # Item 5 is in both lists; items 1,2,3 are only in one
    ranked_a = [1, 2, 5]
    ranked_b = [3, 5]
    result = rrf_fuse(ranked_a, ranked_b)
    assert 5 in result
    # 5 should appear before items only in one list
    pos_5 = result.index(5)
    positions_singles = [result.index(x) for x in (1, 2, 3) if x in result]
    assert all(pos_5 < p for p in positions_singles)


def test_rrf_fuse_empty_second_list_preserves_order():
    ranked_a = [10, 20, 30]
    result = rrf_fuse(ranked_a, [])
    # All items from a should be present
    assert set(result) == {10, 20, 30}


def test_rrf_fuse_returns_all_unique_items():
    ranked_a = [1, 2, 3]
    ranked_b = [2, 3, 4]
    result = rrf_fuse(ranked_a, ranked_b)
    assert set(result) == {1, 2, 3, 4}
    assert len(result) == len(set(result))


def test_rrf_fuse_empty_lists_returns_empty():
    assert rrf_fuse([], []) == []


# ---------------------------------------------------------------------------
# run_rga — guard cases
# ---------------------------------------------------------------------------

def test_run_rga_empty_keywords_returns_empty():
    assert run_rga([], ["/some/file.txt"]) == []


def test_run_rga_empty_file_paths_returns_empty():
    assert run_rga(["keyword"], []) == []


def test_run_rga_raises_runtime_error_on_file_not_found():
    with patch("subprocess.run", side_effect=FileNotFoundError("rga not found")):
        with pytest.raises(RuntimeError, match="rga"):
            run_rga(["keyword"], ["/path/to/file.txt"])
