"""Future cloud/vector backend adapter interfaces.

These classes intentionally avoid importing AWS or database clients. They document the adapter
surface that future Amazon Bedrock, Aurora PostgreSQL pgvector, and Amazon OpenSearch Serverless
integrations must implement.
"""

import numpy as np

from dealerai_ops.rag.interfaces import EmbeddingModel, VectorStore
from dealerai_ops.rag.schemas import DocumentChunk, RetrievedChunk


class BedrockEmbeddingModel(EmbeddingModel):
    """Placeholder adapter for future Amazon Bedrock embeddings."""

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """Embed documents through Bedrock in a future implementation."""
        raise NotImplementedError("Amazon Bedrock embedding adapter is not implemented yet.")

    def embed_query(self, text: str) -> np.ndarray:
        """Embed one query through Bedrock in a future implementation."""
        raise NotImplementedError("Amazon Bedrock embedding adapter is not implemented yet.")


class PgVectorStore(VectorStore):
    """Placeholder adapter for future Aurora PostgreSQL pgvector retrieval."""

    def add_chunks(self, chunks: list[DocumentChunk], embeddings: np.ndarray) -> None:
        """Persist chunks and embeddings to pgvector in a future implementation."""
        raise NotImplementedError("Aurora PostgreSQL pgvector adapter is not implemented yet.")

    def search(self, query_embedding: np.ndarray, top_k: int) -> list[RetrievedChunk]:
        """Search pgvector in a future implementation."""
        raise NotImplementedError("Aurora PostgreSQL pgvector adapter is not implemented yet.")


class OpenSearchServerlessVectorStore(VectorStore):
    """Placeholder adapter for future Amazon OpenSearch Serverless retrieval."""

    def add_chunks(self, chunks: list[DocumentChunk], embeddings: np.ndarray) -> None:
        """Persist chunks and embeddings to OpenSearch Serverless in a future implementation."""
        raise NotImplementedError("OpenSearch Serverless adapter is not implemented yet.")

    def search(self, query_embedding: np.ndarray, top_k: int) -> list[RetrievedChunk]:
        """Search OpenSearch Serverless in a future implementation."""
        raise NotImplementedError("OpenSearch Serverless adapter is not implemented yet.")
