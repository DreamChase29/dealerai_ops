from pathlib import Path

import numpy as np
import pytest

from dealerai_ops.rag.adapters import (
    BedrockEmbeddingModel,
    OpenSearchServerlessVectorStore,
    PgVectorStore,
)
from dealerai_ops.rag.chunking import chunk_sections
from dealerai_ops.rag.evaluation import evaluate_retrieval, load_retrieval_eval_queries
from dealerai_ops.rag.loader import load_knowledge_documents, split_document_sections
from dealerai_ops.rag.local import InMemoryVectorStore, LocalHashingEmbeddingModel
from dealerai_ops.rag.retriever import build_local_retriever, citations_from_chunks

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = ROOT / "knowledge"


def test_loads_synthetic_knowledge_corpus() -> None:
    documents = load_knowledge_documents(KNOWLEDGE_DIR)

    assert len(documents) == 9
    assert {document.document_id for document in documents} == {
        "dealership_policies",
        "maintenance_policies",
        "service_scheduling",
        "warranty_faqs",
        "vehicle_maintenance_faqs",
        "inventory_terminology",
        "customer_privacy",
        "sales_process_faqs",
        "human_escalation_policies",
    }
    assert all(document.synthetic for document in documents)
    assert all("Synthetic" in document.title for document in documents)


def test_section_splitting_and_chunk_metadata() -> None:
    documents = load_knowledge_documents(KNOWLEDGE_DIR)
    sections = [section for document in documents for section in split_document_sections(document)]
    chunks = chunk_sections(sections, max_words=60, overlap_words=10)

    assert len(sections) >= 40
    assert len(chunks) >= len(sections)
    first = chunks[0]
    assert first.document_id
    assert first.title
    assert first.section
    assert first.chunk_id.startswith(first.document_id)
    assert first.source_metadata.document_id == first.document_id
    assert first.source_metadata.synthetic is True


def test_chunking_rejects_invalid_configuration() -> None:
    documents = load_knowledge_documents(KNOWLEDGE_DIR)
    sections = split_document_sections(documents[0])

    with pytest.raises(ValueError, match="max_words"):
        chunk_sections(sections, max_words=0)
    with pytest.raises(ValueError, match="overlap_words"):
        chunk_sections(sections, max_words=10, overlap_words=10)


def test_local_embeddings_are_deterministic() -> None:
    model = LocalHashingEmbeddingModel(n_features=512)
    first = model.embed_query("service slot capacity")
    second = model.embed_query("service slot capacity")

    assert np.allclose(first, second)
    assert first.shape == (512,)


def test_vector_store_requires_index_before_search() -> None:
    store = InMemoryVectorStore()

    with pytest.raises(ValueError, match="not been indexed"):
        store.search(np.array([1.0, 0.0]), top_k=1)


def test_local_retriever_returns_citation_ready_chunks() -> None:
    retriever = build_local_retriever(KNOWLEDGE_DIR)

    results = retriever.retrieve("Does appointment booking require explicit confirmation?", top_k=3)
    citations = citations_from_chunks(results)

    assert results
    assert results[0].document_id == "service_scheduling"
    assert results[0].score >= 0
    assert results[0].source_metadata.source_path.endswith("service_scheduling.md")
    assert citations[0].document_id == results[0].document_id
    assert citations[0].chunk_id == results[0].chunk_id


def test_retrieval_is_deterministic() -> None:
    first = build_local_retriever(KNOWLEDGE_DIR)
    second = build_local_retriever(KNOWLEDGE_DIR)

    first_ids = [
        chunk.chunk_id for chunk in first.retrieve("privacy requests require escalation", 5)
    ]
    second_ids = [
        chunk.chunk_id for chunk in second.retrieve("privacy requests require escalation", 5)
    ]

    assert first_ids == second_ids


def test_retrieval_evaluation_metrics_are_high_enough_for_demo_corpus() -> None:
    retriever = build_local_retriever(KNOWLEDGE_DIR)
    queries = load_retrieval_eval_queries(KNOWLEDGE_DIR / "eval_queries.json")

    metrics = evaluate_retrieval(retriever, queries, k=5)

    assert len(queries) >= 40
    assert metrics["query_count"] == float(len(queries))
    assert metrics["recall_at_5"] >= 0.75
    assert metrics["hit_rate_at_5"] >= 0.90
    assert metrics["mrr"] >= 0.65


def test_retrieval_evaluation_rejects_empty_query_set() -> None:
    retriever = build_local_retriever(KNOWLEDGE_DIR)

    with pytest.raises(ValueError, match="At least one"):
        evaluate_retrieval(retriever, [], k=5)


def test_future_adapter_placeholders_are_explicit() -> None:
    bedrock = BedrockEmbeddingModel()
    pgvector = PgVectorStore()
    opensearch = OpenSearchServerlessVectorStore()

    with pytest.raises(NotImplementedError, match="Bedrock"):
        bedrock.embed_query("test")
    with pytest.raises(NotImplementedError, match="pgvector"):
        pgvector.search(np.array([1.0]), top_k=1)
    with pytest.raises(NotImplementedError, match="OpenSearch"):
        opensearch.search(np.array([1.0]), top_k=1)
