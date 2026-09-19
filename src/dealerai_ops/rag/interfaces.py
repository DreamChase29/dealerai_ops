"""Provider-neutral RAG interfaces."""

from typing import Protocol

import numpy as np

from dealerai_ops.rag.schemas import DocumentChunk, RetrievedChunk


class EmbeddingModel(Protocol):
    """Embedding model interface."""

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """Embed documents into a numeric matrix."""

    def embed_query(self, text: str) -> np.ndarray:
        """Embed one query into a numeric vector."""


class VectorStore(Protocol):
    """Vector store interface."""

    def add_chunks(self, chunks: list[DocumentChunk], embeddings: np.ndarray) -> None:
        """Store chunks and corresponding embeddings."""

    def search(self, query_embedding: np.ndarray, top_k: int) -> list[RetrievedChunk]:
        """Return nearest chunks for a query embedding."""


class Reranker(Protocol):
    """Optional reranking interface."""

    def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        """Rerank retrieved chunks."""
