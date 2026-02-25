"""axiom_app.models.sht — Structure-Header Tree (SHT) builder.

Provides a pure-Python, dependency-free implementation of the SHT document
parser used during structure-aware ingestion.  No Tkinter, no LangChain.

Public API
----------
build_sht_tree(header_candidates, content_spans, source_text) -> list[dict]
    Build a tree of document sections from header annotations and content spans.

SHTNode (dataclass)
    Internal node representation; serialised to plain dicts by build_sht_tree.

_stable_node_id (module-private)
    Deterministic 16-hex-char ID derived from node geometry.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SHTNode:
    id: str
    header_path: list[str]
    level: int
    node_title: str
    node_content: str
    char_span: tuple[int, int]
    page_span: tuple[Optional[int], Optional[int]]
    parent_id: Optional[str]
    children_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "header_path": list(self.header_path),
            "level": self.level,
            "node_title": self.node_title,
            "node_content": self.node_content,
            "char_span": self.char_span,
            "page_span": self.page_span,
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stable_node_id(title: str, header_path: list[str], level: int, start: int, end: int) -> str:
    payload = "|".join([str(level), ">".join(header_path), title.strip().lower(), str(start), str(end)])
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_sht_tree(
    header_candidates: list[dict[str, Any]],
    content_spans: list[dict[str, Any]],
    source_text: str,
) -> list[dict[str, Any]]:
    """Build a structure-header tree (SHT) from headers + spans.

    Rules applied:
    - local-first insertion for content spans
    - rightmost-path insertion for ambiguous headers
    - robustness: node text is a superset of intended section
    - compactness: boundaries stop before the next competing header
    """
    if not header_candidates:
        return []

    sorted_headers = sorted(
        [h for h in header_candidates if str(h.get("text") or "").strip()],
        key=lambda x: int(x.get("char_start") or 0),
    )
    sorted_spans = sorted(content_spans or [], key=lambda x: int(x.get("char_start") or 0))

    root = {
        "id": "root",
        "title": "ROOT",
        "level": 0,
        "char_start": 0,
        "char_end": max(0, len(source_text)),
        "page": None,
        "parent": None,
        "children": [],
        "path": [],
        "spans": [],
    }
    raw_nodes: list[dict[str, Any]] = [root]

    stack: list[dict[str, Any]] = [root]
    rightmost_path: list[dict[str, Any]] = [root]

    for header in sorted_headers:
        level = max(1, int(header.get("header_level") or 1))
        text = str(header.get("text") or "").strip()
        start = int(header.get("char_start") or 0)

        while len(stack) > 1 and stack[-1]["level"] >= level:
            stack.pop()

        parent = stack[-1]
        if rightmost_path and rightmost_path[-1]["level"] < level:
            parent = rightmost_path[-1]

        parent_path = list(parent.get("path") or [])
        new_node = {
            "id": "",
            "title": text,
            "level": level,
            "char_start": start,
            "char_end": max(start, start + len(text)),
            "page": header.get("page"),
            "parent": parent,
            "children": [],
            "path": parent_path + [text],
            "spans": [],
        }
        parent["children"].append(new_node)
        raw_nodes.append(new_node)
        stack.append(new_node)

        rightmost_path = [root]
        cur = new_node
        lineage = []
        while cur is not None:
            lineage.append(cur)
            cur = cur.get("parent")
        rightmost_path = list(reversed(lineage))

    header_nodes = [n for n in raw_nodes if n is not root]

    for span in sorted_spans:
        span_start = int(span.get("char_start") or 0)
        target = None
        for node in header_nodes:
            if node["char_start"] <= span_start:
                target = node
            else:
                break
        if target is None:
            target = root
        target["spans"].append(span)

    for idx, node in enumerate(header_nodes):
        next_header_start = len(source_text)
        for nxt in header_nodes[idx + 1 :]:
            if nxt["level"] <= node["level"]:
                next_header_start = int(nxt["char_start"])
                break

        local_spans = sorted(node.get("spans") or [], key=lambda x: int(x.get("char_start") or 0))
        if local_spans:
            last_span_end = max(int(s.get("char_end") or s.get("char_start") or 0) for s in local_spans)
            intended_end = max(last_span_end, int(node["char_start"]) + len(node["title"]))
        else:
            intended_end = int(node["char_start"]) + len(node["title"])

        compact_end = min(max(int(node["char_start"]), intended_end), next_header_start)
        robust_end = max(compact_end, int(node["char_start"]) + len(node["title"]))
        node["char_end"] = min(max(robust_end, int(node["char_start"])), len(source_text))

    out_nodes: list[SHTNode] = []

    def walk(node: dict[str, Any], parent_id: Optional[str]) -> None:
        if node is not root:
            header_path = list(node.get("path") or [])
            c_start = int(node.get("char_start") or 0)
            c_end = int(node.get("char_end") or c_start)
            text_slice = source_text[c_start:c_end]
            stable_id = _stable_node_id(node.get("title") or "", header_path, int(node.get("level") or 1), c_start, c_end)
            node["id"] = stable_id
            page_values = [node.get("page")]
            for child in node.get("children") or []:
                if child.get("page") is not None:
                    page_values.append(child.get("page"))
            page_values = [p for p in page_values if p is not None]
            page_span = (min(page_values), max(page_values)) if page_values else (None, None)
            out_nodes.append(
                SHTNode(
                    id=stable_id,
                    header_path=header_path,
                    level=int(node.get("level") or 1),
                    node_title=str(node.get("title") or "").strip(),
                    node_content=text_slice,
                    char_span=(c_start, c_end),
                    page_span=page_span,
                    parent_id=parent_id,
                    children_ids=[],
                )
            )
            current_parent_id = stable_id
        else:
            current_parent_id = None

        for child in node.get("children") or []:
            walk(child, current_parent_id)

    walk(root, None)

    by_id = {n.id: n for n in out_nodes}
    for node in out_nodes:
        if node.parent_id and node.parent_id in by_id:
            by_id[node.parent_id].children_ids.append(node.id)

    return [node.to_dict() for node in out_nodes]


# ---------------------------------------------------------------------------
# Developer self-test (no heavy dependencies — run with: python -m axiom_app.models.sht)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _SOURCE = (
        "Introduction\n"
        "This is the intro paragraph.\n\n"
        "Chapter 1: Background\n"
        "Some background text here.\n\n"
        "1.1 Sub-section\n"
        "Details of the sub-section.\n\n"
        "Chapter 2: Results\n"
        "Results text.\n"
    )

    def _char(substr: str) -> int:
        return _SOURCE.index(substr)

    _headers = [
        {"text": "Introduction",        "header_level": 1, "char_start": _char("Introduction"),        "page": 1},
        {"text": "Chapter 1: Background","header_level": 1, "char_start": _char("Chapter 1"),          "page": 2},
        {"text": "1.1 Sub-section",      "header_level": 2, "char_start": _char("1.1 Sub-section"),    "page": 2},
        {"text": "Chapter 2: Results",   "header_level": 1, "char_start": _char("Chapter 2: Results"), "page": 3},
    ]
    _spans = [
        {"char_start": _char("This is"),  "char_end": _char("This is") + 28},
        {"char_start": _char("Some"),     "char_end": _char("Some")    + 26},
        {"char_start": _char("Details"),  "char_end": _char("Details") + 28},
        {"char_start": _char("Results t"),"char_end": _char("Results t") + 13},
    ]

    result = build_sht_tree(_headers, _spans, _SOURCE)

    print(f"Nodes produced : {len(result)}")
    for node in result:
        indent = "  " * (node["level"] - 1)
        print(
            f"{indent}[L{node['level']}] {node['node_title']!r:30s} "
            f"chars={node['char_span']}  pages={node['page_span']}  "
            f"children={node['children_ids']}"
        )

    # Basic assertions
    assert len(result) == 4, f"Expected 4 nodes, got {len(result)}"
    titles = [n["node_title"] for n in result]
    assert "1.1 Sub-section" in titles, "Sub-section node missing"
    l1_nodes = [n for n in result if n["level"] == 1]
    l2_nodes = [n for n in result if n["level"] == 2]
    assert len(l1_nodes) == 3, f"Expected 3 L1 nodes, got {len(l1_nodes)}"
    assert len(l2_nodes) == 1, f"Expected 1 L2 node, got {len(l2_nodes)}"
    # Child linkage: Chapter 1 should reference the sub-section
    ch1 = next(n for n in result if n["node_title"] == "Chapter 1: Background")
    assert len(ch1["children_ids"]) == 1, "Chapter 1 should have one child"
    print("\nAll assertions passed.")
