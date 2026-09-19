"""Knowledge retriever with citation-ready results."""

from pathlib import Path

from dealerai_ops.observability import start_span
from dealerai_ops.rag.chunking import chunk_sections
from dealerai_ops.rag.interfaces import EmbeddingModel, Reranker, VectorStore
from dealerai_ops.rag.loader import load_knowledge_documents, split_document_sections
from dealerai_ops.rag.local import InMemoryVectorStore, LocalHashingEmbeddingModel, NoOpReranker
from dealerai_ops.rag.schemas import Citation, DocumentChunk, RetrievedChunk


class KnowledgeRetriever:
    """Retrieve citation-ready knowledge chunks from indexed documents."""

    def __init__(
        self,
        embedding_model: EmbeddingModel,
        vector_store: VectorStore,
        reranker: Reranker | None = None,
    ) -> None:
        self.embedding_model = embedding_model
        self.vector_store = vector_store
        self.reranker = reranker

    def index_chunks(self, chunks: list[DocumentChunk]) -> None:
        """Embed and index chunks."""
        embeddings = self.embedding_model.embed_documents([chunk.text for chunk in chunks])
        self.vector_store.add_chunks(chunks, embeddings)

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Retrieve top-k chunks for a query."""
        with start_span(
            "retrieval_operation",
            attributes={"top_k": top_k, "query_length": len(query)},
        ) as span:
            query_embedding = self.embedding_model.embed_query(query)
            candidates = self.vector_store.search(query_embedding, top_k=top_k)
            results = (
                candidates
                if self.reranker is None
                else self.reranker.rerank(query, candidates, top_k)
            )
            span.set_attributes(
                {
                    "retrieval_count": len(results),
                    "document_ids": [chunk.document_id for chunk in results],
                    "reranked": self.reranker is not None,
                }
            )
            return results


def build_local_retriever(
    knowledge_dir: str | Path,
    max_words: int = 90,
    overlap_words: int = 18,
) -> KnowledgeRetriever:
    """Build and index the deterministic local retriever."""
    documents = load_knowledge_documents(knowledge_dir)
    sections = [section for document in documents for section in split_document_sections(document)]
    chunks = chunk_sections(sections, max_words=max_words, overlap_words=overlap_words)
    retriever = KnowledgeRetriever(
        embedding_model=LocalHashingEmbeddingModel(),
        vector_store=InMemoryVectorStore(),
        reranker=NoOpReranker(),
    )
    retriever.index_chunks(chunks)
    return retriever


def citations_from_chunks(chunks: list[RetrievedChunk]) -> list[Citation]:
    """Build citations from retrieved chunks."""
    return [
        Citation(
            document_id=chunk.document_id,
            title=chunk.title,
            section=chunk.section,
            chunk_id=chunk.chunk_id,
            source_path=chunk.source_metadata.source_path,
        )
        for chunk in chunks
    ]
