"""tests/test_sht.py — Unit tests for metis_app.models.sht.

No Tk, no heavy ML dependencies.  All inputs are tiny inline strings so
the suite runs in milliseconds.
"""

from __future__ import annotations


from metis_app.models.sht import _stable_node_id, build_sht_tree

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOURCE = (
    "Introduction\n"
    "This is the intro.\n\n"
    "Chapter 1: Background\n"
    "Background text here.\n\n"
    "1.1 Sub-section\n"
    "Details of sub-section.\n\n"
    "Chapter 2: Results\n"
    "Results text.\n"
)


def _pos(substr: str) -> int:
    """Return the char index of *substr* in _SOURCE; fail fast if missing."""
    idx = _SOURCE.find(substr)
    assert idx != -1, f"{substr!r} not found in _SOURCE"
    return idx


_HEADERS = [
    {"text": "Introduction",         "header_level": 1, "char_start": _pos("Introduction"),        "page": 1},
    {"text": "Chapter 1: Background","header_level": 1, "char_start": _pos("Chapter 1"),           "page": 2},
    {"text": "1.1 Sub-section",      "header_level": 2, "char_start": _pos("1.1 Sub-section"),     "page": 2},
    {"text": "Chapter 2: Results",   "header_level": 1, "char_start": _pos("Chapter 2: Results"),  "page": 3},
]

_SPANS = [
    {"char_start": _pos("This is"),    "char_end": _pos("This is")    + 18},
    {"char_start": _pos("Background"), "char_end": _pos("Background") + 20},
    {"char_start": _pos("Details"),    "char_end": _pos("Details")    + 23},
    {"char_start": _pos("Results t"),  "char_end": _pos("Results t")  + 13},
]


# ---------------------------------------------------------------------------
# Empty / trivial inputs
# ---------------------------------------------------------------------------


def test_empty_headers_returns_empty_list():
    result = build_sht_tree([], [], _SOURCE)
    assert result == []


def test_all_blank_header_text_is_filtered():
    blank_headers = [
        {"text": "",  "header_level": 1, "char_start": 0},
        {"text": "  ","header_level": 1, "char_start": 5},
    ]
    result = build_sht_tree(blank_headers, [], _SOURCE)
    assert result == []


def test_single_header_produces_one_node():
    headers = [{"text": "Introduction", "header_level": 1, "char_start": 0}]
    result = build_sht_tree(headers, [], _SOURCE)
    assert len(result) == 1
    assert result[0]["node_title"] == "Introduction"
    assert result[0]["level"] == 1
    assert result[0]["parent_id"] is None
    assert result[0]["children_ids"] == []


# ---------------------------------------------------------------------------
# Node count and structure
# ---------------------------------------------------------------------------


def test_four_headers_produce_four_nodes():
    result = build_sht_tree(_HEADERS, _SPANS, _SOURCE)
    assert len(result) == 4


def test_node_levels_are_correct():
    result = build_sht_tree(_HEADERS, _SPANS, _SOURCE)
    by_title = {n["node_title"]: n for n in result}

    assert by_title["Introduction"]["level"]         == 1
    assert by_title["Chapter 1: Background"]["level"] == 1
    assert by_title["1.1 Sub-section"]["level"]       == 2
    assert by_title["Chapter 2: Results"]["level"]    == 1


# ---------------------------------------------------------------------------
# Parent-child linkage
# ---------------------------------------------------------------------------


def test_subsection_parent_is_chapter1():
    result = build_sht_tree(_HEADERS, _SPANS, _SOURCE)
    by_title = {n["node_title"]: n for n in result}

    ch1 = by_title["Chapter 1: Background"]
    sub = by_title["1.1 Sub-section"]

    assert sub["parent_id"] == ch1["id"], "sub-section's parent_id must equal chapter 1's id"
    assert sub["id"] in ch1["children_ids"], "chapter 1's children_ids must include the sub-section"


def test_top_level_nodes_have_no_parent():
    result = build_sht_tree(_HEADERS, _SPANS, _SOURCE)
    top_level = [n for n in result if n["level"] == 1]
    for node in top_level:
        assert node["parent_id"] is None, f"{node['node_title']!r} should have parent_id=None"


def test_chapter2_has_no_children():
    result = build_sht_tree(_HEADERS, _SPANS, _SOURCE)
    by_title = {n["node_title"]: n for n in result}
    assert by_title["Chapter 2: Results"]["children_ids"] == []


# ---------------------------------------------------------------------------
# ID stability
# ---------------------------------------------------------------------------


def test_ids_are_stable_across_calls():
    r1 = build_sht_tree(_HEADERS, _SPANS, _SOURCE)
    r2 = build_sht_tree(_HEADERS, _SPANS, _SOURCE)
    ids1 = [n["id"] for n in r1]
    ids2 = [n["id"] for n in r2]
    assert ids1 == ids2, "IDs must be deterministic across separate calls"


def test_ids_are_16_hex_chars():
    result = build_sht_tree(_HEADERS, _SPANS, _SOURCE)
    for node in result:
        nid = node["id"]
        assert len(nid) == 16, f"id {nid!r} is not 16 chars"
        assert all(c in "0123456789abcdef" for c in nid), f"id {nid!r} is not lowercase hex"


def test_all_ids_are_unique():
    result = build_sht_tree(_HEADERS, _SPANS, _SOURCE)
    ids = [n["id"] for n in result]
    assert len(ids) == len(set(ids)), "duplicate IDs found"


# ---------------------------------------------------------------------------
# Char spans
# ---------------------------------------------------------------------------


def test_char_spans_are_non_empty():
    result = build_sht_tree(_HEADERS, _SPANS, _SOURCE)
    for node in result:
        start, end = node["char_span"]
        assert end >= start, f"inverted char_span on {node['node_title']!r}: {node['char_span']}"


def test_char_spans_within_source_bounds():
    result = build_sht_tree(_HEADERS, _SPANS, _SOURCE)
    for node in result:
        start, end = node["char_span"]
        assert start >= 0
        assert end <= len(_SOURCE), (
            f"char_span {node['char_span']} exceeds source length {len(_SOURCE)}"
        )


# ---------------------------------------------------------------------------
# to_dict round-trip (SHTNode dataclass)
# ---------------------------------------------------------------------------


def test_to_dict_contains_all_required_keys():
    required = {"id", "header_path", "level", "node_title", "node_content",
                "char_span", "page_span", "parent_id", "children_ids"}
    result = build_sht_tree(_HEADERS, _SPANS, _SOURCE)
    for node in result:
        missing = required - node.keys()
        assert not missing, f"node {node.get('node_title')!r} missing keys: {missing}"


def test_header_path_is_list_of_strings():
    result = build_sht_tree(_HEADERS, _SPANS, _SOURCE)
    for node in result:
        hp = node["header_path"]
        assert isinstance(hp, list)
        assert all(isinstance(s, str) for s in hp)


# ---------------------------------------------------------------------------
# _stable_node_id directly
# ---------------------------------------------------------------------------


def test_stable_node_id_same_input_same_output():
    a = _stable_node_id("Title", ["Root", "Title"], 2, 10, 50)
    b = _stable_node_id("Title", ["Root", "Title"], 2, 10, 50)
    assert a == b


def test_stable_node_id_different_start_different_output():
    a = _stable_node_id("Title", ["Root", "Title"], 2, 10, 50)
    b = _stable_node_id("Title", ["Root", "Title"], 2, 20, 60)
    assert a != b


def test_stable_node_id_length_is_16():
    nid = _stable_node_id("Hello", ["Hello"], 1, 0, 5)
    assert len(nid) == 16
