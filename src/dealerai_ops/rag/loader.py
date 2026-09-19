"""Document loading for the synthetic knowledge corpus."""

from pathlib import Path

from dealerai_ops.rag.normalization import normalize_text
from dealerai_ops.rag.schemas import DocumentSection, KnowledgeDocument


def load_knowledge_documents(knowledge_dir: str | Path) -> list[KnowledgeDocument]:
    """Load markdown knowledge documents from a directory."""
    path = Path(knowledge_dir)
    documents: list[KnowledgeDocument] = []
    for markdown_path in sorted(path.glob("*.md")):
        text = normalize_text(markdown_path.read_text(encoding="utf-8"))
        title = _extract_title(text, markdown_path.stem)
        documents.append(
            KnowledgeDocument(
                document_id=markdown_path.stem,
                title=title,
                text=text,
                source_path=str(markdown_path),
                synthetic=_is_synthetic(text),
            ),
        )
    return documents


def split_document_sections(document: KnowledgeDocument) -> list[DocumentSection]:
    """Split a markdown document into H2 sections."""
    lines = document.text.split("\n")
    sections: list[DocumentSection] = []
    current_section = "Overview"
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            if current_lines:
                sections.append(
                    _section_from_lines(document, current_section, current_lines),
                )
            current_section = line.removeprefix("## ").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append(_section_from_lines(document, current_section, current_lines))
    return sections


def _section_from_lines(
    document: KnowledgeDocument,
    section: str,
    lines: list[str],
) -> DocumentSection:
    return DocumentSection(
        document_id=document.document_id,
        title=document.title,
        section=section,
        text=normalize_text("\n".join(lines)),
        source_path=document.source_path,
        synthetic=document.synthetic,
    )


def _extract_title(text: str, fallback: str) -> str:
    for line in text.split("\n"):
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return fallback.replace("_", " ").title()


def _is_synthetic(text: str) -> bool:
    lowered = text.lower()
    return "fictional/synthetic demonstration material" in lowered
