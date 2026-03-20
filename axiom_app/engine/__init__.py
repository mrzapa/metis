"""Public engine entrypoints."""

from axiom_app.engine.indexing import IndexBuildRequest, IndexBuildResult, build_index
from axiom_app.engine.index_registry import get_index, list_indexes
from axiom_app.engine.querying import (
    DirectQueryRequest,
    DirectQueryResult,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    RagQueryRequest,
    RagQueryResult,
    knowledge_search,
    query_direct,
    query_rag,
)
from axiom_app.engine.streaming import stream_rag_answer

__all__ = [
    "DirectQueryRequest",
    "DirectQueryResult",
    "IndexBuildRequest",
    "IndexBuildResult",
    "KnowledgeSearchRequest",
    "KnowledgeSearchResult",
    "RagQueryRequest",
    "RagQueryResult",
    "build_index",
    "get_index",
    "knowledge_search",
    "list_indexes",
    "query_direct",
    "query_rag",
    "stream_rag_answer",
]
