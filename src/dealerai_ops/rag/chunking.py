"""Chunking for dealership knowledge documents."""

from collections.abc import Iterable

from dealerai_ops.rag.schemas import DocumentChunk, DocumentSection, SourceMetadata


def chunk_sections(
    sections: Iterable[DocumentSection],
    max_words: int = 90,
    overlap_words: int = 18,
) -> list[DocumentChunk]:
    """Chunk sections by word count with small overlap for context continuity."""
    if max_words <= 0:
        raise ValueError("max_words must be positive.")
    if overlap_words < 0 or overlap_words >= max_words:
        raise ValueError("overlap_words must be non-negative and smaller than max_words.")

    chunks: list[DocumentChunk] = []
    per_document_counter: dict[str, int] = {}
    for section in sections:
        words = section.text.split()
        if not words:
            continue
        start = 0
        while start < len(words):
            end = min(start + max_words, len(words))
            chunk_words = words[start:end]
            per_document_counter[section.document_id] = (
                per_document_counter.get(section.document_id, 0) + 1
            )
            chunk_number = per_document_counter[section.document_id]
            chunk_id = f"{section.document_id}::chunk_{chunk_number:04d}"
            source_metadata = SourceMetadata(
                document_id=section.document_id,
                title=section.title,
                section=section.section,
                source_path=section.source_path,
                synthetic=section.synthetic,
            )
            chunks.append(
                DocumentChunk(
                    document_id=section.document_id,
                    title=section.title,
                    section=section.section,
                    chunk_id=chunk_id,
                    text=" ".join(chunk_words),
                    source_metadata=source_metadata,
                ),
            )
            if end == len(words):
                break
            start = end - overlap_words
    return chunks
