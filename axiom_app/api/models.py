"""Pydantic API models that mirror engine request/response dataclasses."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from axiom_app.engine import (
    DirectQueryRequest,
    DirectQueryResult,
    IndexBuildRequest,
    IndexBuildResult,
    RagQueryRequest,
    RagQueryResult,
)


class IndexBuildRequestModel(BaseModel):
    document_paths: list[str] = Field(min_length=1)
    settings: dict[str, Any]
    index_id: str | None = None

    model_config = ConfigDict(extra="forbid")

    def to_engine(self) -> IndexBuildRequest:
        return IndexBuildRequest(
            document_paths=self.document_paths,
            settings=dict(self.settings),
            index_id=self.index_id,
        )


class IndexBuildResultModel(BaseModel):
    manifest_path: str
    index_id: str
    document_count: int
    chunk_count: int
    embedding_signature: str
    vector_backend: str

    @classmethod
    def from_engine(cls, result: IndexBuildResult) -> "IndexBuildResultModel":
        return cls(
            manifest_path=str(result.manifest_path),
            index_id=result.index_id,
            document_count=result.document_count,
            chunk_count=result.chunk_count,
            embedding_signature=result.embedding_signature,
            vector_backend=result.vector_backend,
        )


class RagQueryRequestModel(BaseModel):
    manifest_path: str
    question: str
    settings: dict[str, Any]
    run_id: str | None = None

    model_config = ConfigDict(extra="forbid")

    def to_engine(self) -> RagQueryRequest:
        return RagQueryRequest(
            manifest_path=Path(self.manifest_path),
            question=self.question,
            settings=dict(self.settings),
            run_id=self.run_id,
        )


class RagQueryResultModel(BaseModel):
    run_id: str
    answer_text: str
    sources: list[dict[str, Any]]
    context_block: str
    top_score: float
    selected_mode: str

    @classmethod
    def from_engine(cls, result: RagQueryResult) -> "RagQueryResultModel":
        return cls(
            run_id=result.run_id,
            answer_text=result.answer_text,
            sources=result.sources,
            context_block=result.context_block,
            top_score=result.top_score,
            selected_mode=result.selected_mode,
        )


class DirectQueryRequestModel(BaseModel):
    prompt: str
    settings: dict[str, Any]
    run_id: str | None = None

    model_config = ConfigDict(extra="forbid")

    def to_engine(self) -> DirectQueryRequest:
        return DirectQueryRequest(
            prompt=self.prompt,
            settings=dict(self.settings),
            run_id=self.run_id,
        )


class DirectQueryResultModel(BaseModel):
    run_id: str
    answer_text: str
    selected_mode: str

    @classmethod
    def from_engine(cls, result: DirectQueryResult) -> "DirectQueryResultModel":
        return cls(
            run_id=result.run_id,
            answer_text=result.answer_text,
            selected_mode=result.selected_mode,
        )
