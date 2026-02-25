"""axiom_app.utils — Pure-Python helpers shared across layers.

Planned contents (to be migrated from agentic_rag_gui.py):
  - embeddings.py   : MockEmbeddings, LocalSentenceTransformerEmbeddings
  - llm_backends.py : MockChatModel, LocalLlamaCppChatModel
  - ingestion_sht.py: build_sht_tree(), _stable_node_id()
  - trace.py        : TraceStore
  - lazy_imports.py : _lazy_import_langchain/core/chroma/llama_cpp
  - palette.py      : _pal() color-lookup helper
"""
