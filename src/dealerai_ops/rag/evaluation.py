"""Retrieval evaluation metrics for the synthetic knowledge corpus."""

import json
from pathlib import Path

from pydantic import TypeAdapter

from dealerai_ops.rag.retriever import KnowledgeRetriever
from dealerai_ops.rag.schemas import RetrievalQuery

RetrievalQueryList = TypeAdapter(list[RetrievalQuery])


def load_retrieval_eval_queries(path: str | Path) -> list[RetrievalQuery]:
    """Load retrieval evaluation queries from JSON."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return RetrievalQueryList.validate_python(payload)


def evaluate_retrieval(
    retriever: KnowledgeRetriever,
    queries: list[RetrievalQuery],
    k: int = 5,
) -> dict[str, float]:
    """Calculate Recall@K, MRR, and Hit Rate@K."""
    if not queries:
        raise ValueError("At least one evaluation query is required.")
    recall_values: list[float] = []
    reciprocal_ranks: list[float] = []
    hits: list[float] = []

    for query in queries:
        retrieved = retriever.retrieve(query.query, top_k=k)
        retrieved_ids = [chunk.document_id for chunk in retrieved]
        relevant = set(query.relevant_document_ids)
        found_ranks = [
            index + 1 for index, document_id in enumerate(retrieved_ids) if document_id in relevant
        ]
        found_documents = set(retrieved_ids).intersection(relevant)
        recall_values.append(len(found_documents) / len(relevant))
        reciprocal_ranks.append(1.0 / found_ranks[0] if found_ranks else 0.0)
        hits.append(1.0 if found_ranks else 0.0)

    return {
        f"recall_at_{k}": sum(recall_values) / len(recall_values),
        "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks),
        f"hit_rate_at_{k}": sum(hits) / len(hits),
        "query_count": float(len(queries)),
    }
