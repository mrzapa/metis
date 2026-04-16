"""Lightweight knowledge-graph utilities used by METIS ingestion/retrieval.

The implementation provides two extraction strategies:

1. **Rule-based (default)**: stdlib-only heuristics — works in constrained
   environments without additional dependencies.
2. **spaCy-enhanced (optional)**: when spaCy is installed and a model is
   available, uses NER for higher-quality entity extraction with typed labels
   (PERSON, ORG, GPE, PRODUCT, etc.) and supports multilingual documents.

To enable spaCy extraction, install spaCy and a language model::

    pip install spacy
    python -m spacy download en_core_web_sm
"""

from __future__ import annotations

from collections import Counter, deque
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

_log = logging.getLogger(__name__)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "for", "of", "in", "on", "at", "with",
    "from", "by", "as", "is", "are", "was", "were", "be", "been", "being", "that",
    "this", "it", "its", "their", "his", "her", "our", "your", "they", "we", "you",
}

# Cached spaCy NLP pipeline (loaded lazily on first use).
_spacy_nlp: Any = None
_spacy_available: bool | None = None  # None = not yet checked


@dataclass(slots=True)
class KnowledgeGraph:
    """Simple directed multi-relational graph.

    Nodes are canonical entity names (lowercase strings). Edges are stored as
    adjacency lists with relation labels.
    """

    nodes: dict[str, dict[str, str]] = field(default_factory=dict)
    edges: dict[str, dict[str, set[str]]] = field(default_factory=dict)

    def add_node(
        self,
        entity: str,
        *,
        entity_type: str = "ENTITY",
        description: str = "",
    ) -> None:
        canonical = canonicalize_entity(entity)
        if not canonical:
            return
        existing = self.nodes.get(canonical)
        if existing is None:
            attrs: dict[str, str] = {"type": entity_type}
            if description:
                attrs["description"] = description.strip()
            self.nodes[canonical] = attrs
            return
        # Promote a non-default type if the new extraction is more specific.
        if existing.get("type", "ENTITY") in ("ENTITY", "OTHER", "PROPER_NOUN") and entity_type:
            existing["type"] = entity_type
        if description:
            _merge_description(existing, description)

    def add_edge(self, source: str, relation: str, target: str) -> None:
        src = canonicalize_entity(source)
        tgt = canonicalize_entity(target)
        rel = relation.strip().lower()
        if not src or not tgt or src == tgt or not rel:
            return
        self.add_node(src)
        self.add_node(tgt)
        self.edges.setdefault(src, {}).setdefault(tgt, set()).add(rel)

    def neighbors(self, entity: str) -> set[str]:
        return set(self.edges.get(canonicalize_entity(entity), {}).keys())

    def to_dict(self) -> dict[str, Any]:
        """Serialise the graph to a JSON-compatible dictionary."""
        return {
            "nodes": {name: dict(attrs) for name, attrs in self.nodes.items()},
            "edges": {
                src: {tgt: list(rels) for tgt, rels in tgt_map.items()}
                for src, tgt_map in self.edges.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeGraph":
        """Reconstruct a graph from a serialised dictionary."""
        graph = cls()
        for name, attrs in (data.get("nodes") or {}).items():
            graph.nodes[name] = dict(attrs)
        for src, tgt_map in (data.get("edges") or {}).items():
            for tgt, rels in tgt_map.items():
                graph.edges.setdefault(src, {})[tgt] = set(rels)
        return graph


def _load_spacy() -> Any:
    """Attempt to load a spaCy NLP pipeline; return None on failure."""
    global _spacy_nlp, _spacy_available  # noqa: PLW0603
    if _spacy_available is False:
        return None
    if _spacy_nlp is not None:
        return _spacy_nlp

    try:
        import spacy  # type: ignore[import-untyped]

        # Try common English models in order of preference (smallest first for
        # fast startup; users with a large model benefit automatically).
        for model_name in ("en_core_web_sm", "en_core_web_md", "en_core_web_lg"):
            try:
                _spacy_nlp = spacy.load(model_name, disable=["parser", "lemmatizer"])
                _spacy_available = True
                return _spacy_nlp
            except OSError:
                continue

        # No English model found — fall back to rule-based extraction.
        _spacy_available = False
        return None
    except ImportError:
        _spacy_available = False
        return None


def _extract_entities_spacy(chunk: str) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
    """spaCy-based entity extraction with typed NER labels."""
    nlp = _load_spacy()
    if nlp is None:
        return extract_entities_and_relations(chunk)

    doc = nlp(chunk)
    entities: list[tuple[str, str]] = []
    seen_texts: set[str] = set()

    for ent in doc.ents:
        text = ent.text.strip()
        label = ent.label_
        if not text or text.lower() in _STOPWORDS:
            continue
        canonical = canonicalize_entity(text)
        if canonical and canonical not in seen_texts:
            seen_texts.add(canonical)
            entities.append((label, text))

    # Relation extraction remains heuristic even with spaCy; a dedicated
    # relation extractor (e.g., a cross-encoder) would improve this.
    _, relations = extract_entities_and_relations(chunk)
    return entities, relations



def chunk_text(text: str, max_tokens: int = 500) -> list[str]:
    """Split a document into chunks by rough token count."""
    words = re.findall(r"\w+", text)
    if max_tokens <= 0:
        raise ValueError("max_tokens must be > 0")
    return [" ".join(words[i:i + max_tokens]) for i in range(0, len(words), max_tokens)]



def canonicalize_entity(text: str) -> str:
    normalized = re.sub(r"[^\w\s]", "", text).strip().lower()
    return re.sub(r"\s+", " ", normalized)


def _merge_description(attrs: dict[str, str], new_desc: str) -> None:
    """Merge a new description into an entity's existing attrs in place.

    Keeps the descriptions short by deduplicating sentences (case-insensitive)
    and capping total length, so a frequently-mentioned entity does not
    accumulate an unbounded blob.
    """
    new_desc = new_desc.strip()
    if not new_desc:
        return
    existing = attrs.get("description", "").strip()
    if not existing:
        attrs["description"] = new_desc[:600]
        return
    seen = {part.strip().lower() for part in existing.split(" | ") if part.strip()}
    if new_desc.lower() in seen:
        return
    merged = f"{existing} | {new_desc}"
    attrs["description"] = merged[:600]



def extract_entities_and_relations(chunk: str) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
    """Heuristic entity/relation extraction.

    Entities: contiguous title-cased spans (e.g. "New York", "Ada Lovelace").
    Relations: simplistic ``<entity> <verb> <entity>`` patterns.
    """
    entities: list[tuple[str, str]] = []
    for match in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", chunk):
        entities.append(("PROPER_NOUN", match.group(1)))

    relations: list[tuple[str, str, str]] = []
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]*", chunk)
    for i in range(1, len(tokens) - 1):
        subj, rel, obj = tokens[i - 1], tokens[i], tokens[i + 1]
        if subj[:1].isupper() and obj[:1].isupper() and rel.isalpha():
            relations.append((subj, rel.lower(), obj))
    return entities, relations



def glean_relationships(relations: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    seen: set[tuple[str, str, str]] = set()
    cleaned: list[tuple[str, str, str]] = []
    for src, rel, tgt in relations:
        key = (canonicalize_entity(src), rel.strip().lower(), canonicalize_entity(tgt))
        if not key[0] or not key[2] or key[0] == key[2] or key in seen:
            continue
        seen.add(key)
        cleaned.append((src, rel, tgt))
    return cleaned



def normalise_entities(entities: list[tuple[str, str]]) -> list[tuple[str, str]]:
    normalized: list[tuple[str, str]] = []
    for label, text in entities:
        canonical = canonicalize_entity(text)
        if canonical and canonical not in _STOPWORDS:
            normalized.append((label, canonical))
    return normalized


def llm_extract_entities_and_relations(
    text: str,
    llm: Any,
    *,
    max_entities: int = 30,
    max_relations: int = 20,
    max_passes: int = 1,
    return_descriptions: bool = False,
) -> (
    tuple[list[tuple[str, str]], list[tuple[str, str, str]]]
    | tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]
):
    """LLM-powered entity and relationship extraction with few-shot examples.

    Sends a structured prompt to the LLM asking it to extract named entities
    and subject-verb-object triples in JSON format.  Falls back to
    ``extract_entities_and_relations`` on any failure.

    Parameters
    ----------
    text:
        The document chunk to analyse.
    llm:
        Any object with an ``.invoke(messages)`` method returning an object
        with a ``.content`` attribute (LangChain ``BaseChatModel`` protocol).
    max_entities:
        Upper bound on returned entities (most salient first).
    max_relations:
        Upper bound on returned relation triples.
    max_passes:
        Number of extraction passes ("gleaning"). When > 1, the LLM is
        re-prompted with already-extracted entities and asked to surface any
        it missed; the loop stops early once a pass yields no new entities.
        Cap is hard-clamped to 5 to bound cost.
    return_descriptions:
        When ``True``, returned entities are 3-tuples
        ``(entity_type, entity_text, description)`` instead of 2-tuples.

    Returns
    -------
    entities:
        List of ``(entity_type, entity_text)`` tuples (or 3-tuples with
        descriptions when ``return_descriptions=True``).
    relations:
        List of ``(subject, predicate, object)`` triples.
    """
    desc_clause = (
        '. Each entity also includes a one-sentence description grounded only in this text'
        if return_descriptions else ''
    )
    _entity_schema = (
        '{"type": "<TYPE>", "text": "<text>", "description": "<one-sentence>"}'
        if return_descriptions else
        '{"type": "<TYPE>", "text": "<text>"}'
    )
    _example_entities_1 = (
        '[{"type": "ORG", "text": "Apple Inc.", "description": "Acquired Shazam in 2018."}, '
        '{"type": "ORG", "text": "Shazam", "description": "Acquired by Apple in 2018."}, '
        '{"type": "PERSON", "text": "Tim Cook", "description": "Announced the Shazam acquisition."}]'
        if return_descriptions else
        '[{"type": "ORG", "text": "Apple Inc."}, {"type": "ORG", "text": "Shazam"}, '
        '{"type": "PERSON", "text": "Tim Cook"}]'
    )
    _example_entities_2 = (
        '[{"type": "OTHER", "text": "GDPR", "description": "EU regulation effective May 2018."}, '
        '{"type": "GPE", "text": "EU", "description": "Bloc whose member states apply GDPR."}]'
        if return_descriptions else
        '[{"type": "OTHER", "text": "GDPR"}, {"type": "GPE", "text": "EU"}]'
    )
    _FEW_SHOT = (
        'Example 1\n'
        'Input: "Apple Inc. acquired Shazam in 2018 for $400 million. Tim Cook announced the deal."\n'
        f'Output: {{"entities": {_example_entities_1}, '
        '"relations": [{"subject": "Apple Inc.", "predicate": "acquired", '
        '"object": "Shazam"}, {"subject": "Tim Cook", "predicate": "announced", "object": "deal"}]}\n\n'
        'Example 2\n'
        'Input: "The GDPR regulation came into force in May 2018 across all EU member states."\n'
        f'Output: {{"entities": {_example_entities_2}, '
        '"relations": [{"subject": "GDPR", "predicate": "applies_to", "object": "EU member states"}]}'
    )

    system = (
        "You are a precise information-extraction assistant.\n"
        f"Extract named entities and subject-predicate-object relationships from the text{desc_clause}.\n\n"
        "Entity types: PERSON, ORG, GPE, PRODUCT, CONCEPT, EVENT, OTHER.\n\n"
        "Rejection rules — do NOT include:\n"
        "  - stopwords or pronouns (it, they, this, that, …)\n"
        "  - generic verbs: is, are, have, has, had, be, been, being, do, does, did\n"
        "  - single-character tokens\n"
        "  - numbers-only strings\n\n"
        f"Return at most {max_entities} entities and {max_relations} relations, "
        "most salient first.\n\n"
        "Output ONLY valid JSON in this exact schema, no prose, no markdown fences:\n"
        f'{{"entities": [{_entity_schema}], '
        '"relations": [{"subject": "<subj>", "predicate": "<pred>", "object": "<obj>"}]}\n\n'
        + _FEW_SHOT
    )

    user_text = text[:3000] if len(text) > 3000 else text
    base_user = f'Input: "{user_text}"'
    passes = max(1, min(int(max_passes or 1), 5))

    entities_with_desc: list[tuple[str, str, str]] = []
    relations: list[tuple[str, str, str]] = []
    seen_entity_keys: set[str] = set()
    first_pass_failed = False

    for pass_idx in range(passes):
        if pass_idx == 0:
            user = base_user
        else:
            already = ", ".join(sorted({e[1] for e in entities_with_desc})[:50])
            user = (
                f"{base_user}\n\n"
                f"You already extracted: [{already}].\n"
                "Return ONLY entities and relations you previously MISSED. "
                'If nothing was missed, return {"entities": [], "relations": []}.'
            )

        try:
            response = llm.invoke([
                {"type": "system", "content": system},
                {"type": "human", "content": user},
            ])
            raw = response.content

            stripped = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
            stripped = re.sub(r"```\s*$", "", stripped.strip())
            parsed = json.loads(stripped)
        except Exception as exc:  # noqa: BLE001
            _log.debug(
                "llm_extract pass %d/%d failed: %s", pass_idx + 1, passes, exc
            )
            if pass_idx == 0:
                first_pass_failed = True
            break  # later-pass failures keep what earlier passes produced

        new_count = 0
        for item in parsed.get("entities", []) or []:
            txt = item.get("text")
            typ = item.get("type")
            if not txt or not typ:
                continue
            key = canonicalize_entity(txt)
            if not key or key in seen_entity_keys:
                continue
            seen_entity_keys.add(key)
            entities_with_desc.append((typ, txt, str(item.get("description") or "")))
            new_count += 1

        for r in parsed.get("relations", []) or []:
            if r.get("subject") and r.get("predicate") and r.get("object"):
                relations.append((r["subject"], r["predicate"], r["object"]))

        if pass_idx > 0 and new_count == 0:
            break  # gleaning converged

    if first_pass_failed:
        ents, rels = extract_entities_and_relations(text)
        if return_descriptions:
            return [(t, e, "") for t, e in ents], rels
        return ents, rels

    relations = glean_relationships(relations)

    if return_descriptions:
        normalized = [
            (label, canonicalize_entity(text), desc)
            for label, text, desc in entities_with_desc
            if canonicalize_entity(text) and canonicalize_entity(text) not in _STOPWORDS
        ]
        return normalized, relations

    entities = normalise_entities([(label, text) for label, text, _ in entities_with_desc])
    return entities, relations



def build_knowledge_graph(
    chunks: list[str],
    *,
    use_spacy: bool = True,
) -> tuple[KnowledgeGraph, dict[str, set[int]]]:
    """Build graph and reverse index mapping entity -> chunk indices.

    Args:
        chunks: Text chunks to extract entities and relations from.
        use_spacy: When ``True`` (default), use spaCy NER if available,
            otherwise fall back to the rule-based heuristic extractor.
    """
    graph = KnowledgeGraph()
    entity_to_chunks: dict[str, set[int]] = {}

    extractor = _extract_entities_spacy if use_spacy else extract_entities_and_relations

    for idx, chunk in enumerate(chunks):
        entities, rels = extractor(chunk)
        normalized_entities = normalise_entities(entities)
        cleaned_rels = glean_relationships(rels)

        for label, entity in normalized_entities:
            graph.add_node(entity, entity_type=label)
            entity_to_chunks.setdefault(entity, set()).add(idx)

        for src, rel, tgt in cleaned_rels:
            graph.add_edge(src, rel, tgt)

    return graph, entity_to_chunks



def extract_query_entities(question: str) -> list[str]:
    entities, _ = extract_entities_and_relations(question)
    candidates = [canonicalize_entity(text) for _label, text in entities]

    if not candidates:
        token_counts = Counter(re.findall(r"\w+", question.lower()))
        candidates = [tok for tok, _ in token_counts.most_common(3) if tok not in _STOPWORDS]

    deduped: list[str] = []
    for item in candidates:
        if item and item not in deduped:
            deduped.append(item)
    return deduped



def traverse_graph(graph: KnowledgeGraph, start_entity: str, depth: int = 2) -> list[str]:
    """BFS traversal over outgoing edges up to ``depth``."""
    start = canonicalize_entity(start_entity)
    if not start:
        return []
    visited = {start}
    queue = deque([(start, 0)])
    ordered: list[str] = []

    while queue:
        node, level = queue.popleft()
        ordered.append(node)
        if level >= depth:
            continue
        for neighbor in graph.neighbors(node):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            queue.append((neighbor, level + 1))

    return ordered



def collect_graph_chunk_candidates(
    *,
    graph: KnowledgeGraph,
    entity_to_chunks: dict[str, set[int]],
    question: str,
    mode: str,
    limit: int,
) -> list[int]:
    """Return chunk ids suggested by graph traversal mode.

    Modes:
    - naive / bypass: no graph expansion
    - local: depth=1 from query entities
    - global: depth=3 from query entities
    - hybrid / mix: depth=2 from query entities
    """
    mode_norm = (mode or "hybrid").strip().lower()
    if mode_norm in {"naive", "bypass"}:
        return []

    depth_by_mode = {"local": 1, "global": 3, "hybrid": 2, "mix": 2}
    depth = depth_by_mode.get(mode_norm, 2)

    out: list[int] = []
    seen: set[int] = set()
    for entity in extract_query_entities(question):
        for reachable in traverse_graph(graph, entity, depth=depth):
            for chunk_idx in sorted(entity_to_chunks.get(reachable, set())):
                if chunk_idx in seen:
                    continue
                seen.add(chunk_idx)
                out.append(chunk_idx)
                if len(out) >= limit:
                    return out
    return out
