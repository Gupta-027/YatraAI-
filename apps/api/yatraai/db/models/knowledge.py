"""RAG knowledge base: cited source documents, semantic chunks, embeddings."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from yatraai.config import get_settings
from yatraai.db.base import (
    GUID,
    Base,
    JSONType,
    TimestampMixin,
    TZDateTime,
    UUIDPrimaryKeyMixin,
    VectorType,
)

_EMBEDDING_DIM = get_settings().embedding_dim


class SourceDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A curated, cited knowledge document scoped to a cluster/attraction."""

    __tablename__ = "source_documents"

    doc_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    cluster_slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    attraction_slug: Mapped[str | None] = mapped_column(String(96), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content_category: Mapped[str] = mapped_column(
        String(40), nullable=False
    )  # history | significance | architecture | etiquette | accessibility | practical | facts
    body: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="official", nullable=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    last_verified_at: Mapped[date | None] = mapped_column(Date)
    time_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_srcdoc_cluster_attr", "cluster_slug", "attraction_slug"),)


class DocumentChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Semantic chunk (one topic of one attraction), not a blind character split."""

    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Denormalised for cheap metadata filtering during retrieval.
    cluster_slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    attraction_slug: Mapped[str | None] = mapped_column(String(96), index=True)
    content_category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="official", nullable=False)
    last_verified_at: Mapped[date | None] = mapped_column(Date)
    keywords: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    document: Mapped[SourceDocument] = relationship(back_populates="chunks")
    embedding: Mapped[ChunkEmbedding | None] = relationship(
        back_populates="chunk", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_doc_index"),
        Index("ix_chunk_filter", "cluster_slug", "content_category"),
    )


class ChunkEmbedding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chunk_embeddings"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[list] = mapped_column(VectorType(_EMBEDDING_DIM), nullable=False)
    norm: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    chunk: Mapped[DocumentChunk] = relationship(back_populates="embedding")


class RagEvaluation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One evaluated question from the benchmark set."""

    __tablename__ = "rag_evaluations"

    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    question_id: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    cluster_slug: Mapped[str | None] = mapped_column(String(64))
    attraction_slug: Mapped[str | None] = mapped_column(String(96))
    retrieval_precision: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    retrieval_recall: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    context_relevance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    faithfulness: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    citation_correctness: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    answer_completeness: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    abstained: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    retrieved_chunk_ids: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    meta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
