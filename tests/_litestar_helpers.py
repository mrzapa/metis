"""Shared test helpers for the Litestar API test suite.

The Litestar API splits FastAPI's former ``metis_app.api.app`` module into
per-tag route modules under ``metis_app.api_litestar.routes``.  Most tests used
to patch ``api_app_module.WorkspaceOrchestrator`` — this helper patches the
name across every route module that imports it so a single test monkeypatch
still works.
"""

from __future__ import annotations

from metis_app.api_litestar.routes import (
    assistant,
    atlas,
    autonomous,
    core,
    improvements,
    index,
    query,
    web_graph,
)

# Route modules that import WorkspaceOrchestrator at top level.
_WORKSPACE_ORCHESTRATOR_MODULES = (
    assistant,
    atlas,
    autonomous,
    core,
    improvements,
    index,
    query,
    web_graph,
)


def patch_workspace_orchestrator(monkeypatch, factory):
    """Patch ``WorkspaceOrchestrator`` across every Litestar route module."""
    for mod in _WORKSPACE_ORCHESTRATOR_MODULES:
        monkeypatch.setattr(mod, "WorkspaceOrchestrator", factory, raising=False)


def patch_trace_store(monkeypatch, factory):
    """Patch ``TraceStore`` factories used by the core route."""
    monkeypatch.setattr(core, "TraceStore", factory, raising=False)


def patch_execute_nyx_install_action(monkeypatch, fn):
    monkeypatch.setattr(core, "execute_nyx_install_action", fn, raising=False)


def patch_rag_stream_manager(monkeypatch, manager):
    monkeypatch.setattr(query, "_RAG_STREAM_MANAGER", manager, raising=False)
