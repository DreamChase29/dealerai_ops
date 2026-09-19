"""Schemas for knowledge retrieval and citations."""

from pydantic import BaseModel, ConfigDict, Field


class SourceMetadata(BaseModel):
    """Source metadata attached to every retrieved chunk."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str
    section: str
    source_path: str
    synthetic: bool = True


class KnowledgeDocument(BaseModel):
    """Normalized knowledge document."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str
    text: str
    source_path: str
    synthetic: bool = True


class DocumentSection(BaseModel):
    """A titled section extracted from a knowledge document."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str
    section: str
    text: str
    source_path: str
    synthetic: bool = True


class DocumentChunk(BaseModel):
    """Chunk indexed for retrieval."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str
    section: str
    chunk_id: str
    text: str
    source_metadata: SourceMetadata


class RetrievedChunk(BaseModel):
    """Retrieved chunk with score and citation-ready metadata."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str
    section: str
    chunk_id: str
    score: float = Field(ge=0)
    text: str
    source_metadata: SourceMetadata


class Citation(BaseModel):
    """Citation extracted from a retrieved chunk."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str
    section: str
    chunk_id: str
    source_path: str


class RetrievalQuery(BaseModel):
    """Evaluation query with known relevant documents."""

    model_config = ConfigDict(extra="forbid")

    query_id: str
    query: str
    relevant_document_ids: list[str]
