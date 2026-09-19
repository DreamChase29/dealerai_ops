"""Text normalization helpers for retrieval."""

import re

WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Normalize text while preserving readable section content."""
    normalized = text.replace("\ufeff", "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in normalized.split("\n")]
    return "\n".join(line for line in lines if line)
