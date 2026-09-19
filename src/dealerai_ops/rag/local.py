"""Deterministic local embedding and vector store implementations."""

import numpy as np
from numpy.typing import NDArray
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.preprocessing import normalize

from dealerai_ops.rag.interfaces import EmbeddingModel, Reranker, VectorStore
from dealerai_ops.rag.schemas import DocumentChunk, RetrievedChunk


class LocalHashingEmbeddingModel(EmbeddingModel):
    """Deterministic local embeddings based on hashed word and bigram features."""

    def __init__(self, n_features: int = 4096) -> None:
        self.vectorizer = HashingVectorizer(
            n_features=n_features,
            alternate_sign=False,
            norm=None,
            lowercase=True,
            ngram_range=(1, 2),
        )

    def embed_documents(self, texts: list[str]) -> NDArray[np.float64]:
        """Embed document texts into L2-normalized dense vectors."""
        matrix = self.vectorizer.transform(texts)
        return np.asarray(normalize(matrix, norm="l2").toarray(), dtype=np.float64)

    def embed_query(self, text: str) -> NDArray[np.float64]:
        """Embed a query into a L2-normalized dense vector."""
        matrix = self.vectorizer.transform([text])
        return np.asarray(normalize(matrix, norm="l2").toarray()[0], dtype=np.float64)


class InMemoryVectorStore(VectorStore):
    """In-memory cosine similarity vector store for deterministic tests."""

    def __init__(self) -> None:
        self._chunks: list[DocumentChunk] = []
        self._embeddings: np.ndarray | None = None

    def add_chunks(self, chunks: list[DocumentChunk], embeddings: np.ndarray) -> None:
        """Store chunks and embeddings."""
        if len(chunks) != embeddings.shape[0]:
            raise ValueError("Chunk count must match embedding rows.")
        self._chunks = list(chunks)
        self._embeddings = embeddings

    def search(self, query_embedding: np.ndarray, top_k: int) -> list[RetrievedChunk]:
        """Return top-k chunks by cosine similarity."""
        if self._embeddings is None:
            raise ValueError("Vector store has not been indexed.")
        if top_k <= 0:
            raise ValueError("top_k must be positive.")
        scores = self._embeddings @ query_embedding
        ordered_indices = np.argsort(scores)[::-1][:top_k]
        results: list[RetrievedChunk] = []
        for index in ordered_indices:
            chunk = self._chunks[int(index)]
            results.append(
                RetrievedChunk(
                    document_id=chunk.document_id,
                    title=chunk.title,
                    section=chunk.section,
                    chunk_id=chunk.chunk_id,
                    score=float(max(scores[int(index)], 0.0)),
                    text=chunk.text,
                    source_metadata=chunk.source_metadata,
                ),
            )
        return results


class NoOpReranker(Reranker):
    """Default reranker that preserves vector-store ordering."""

    def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        """Return chunks unchanged up to top_k."""
        return chunks[:top_k]
