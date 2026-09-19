"""Factories for provider-independent agent components."""

from pathlib import Path

from dealerai_ops.agents.bedrock import BedrockLLMProvider
from dealerai_ops.agents.providers import LLMProvider, RuleBasedLocalLLMProvider
from dealerai_ops.core.config import Settings
from dealerai_ops.rag.retriever import KnowledgeRetriever, build_local_retriever


def build_llm_provider(settings: Settings) -> LLMProvider:
    """Build the configured LLM provider.

    Local mode is deterministic and requires no paid APIs. Bedrock mode is optional and only imports
    boto3 when selected.
    """
    provider = settings.llm_provider.lower()
    if provider == "local":
        return RuleBasedLocalLLMProvider()
    if provider == "bedrock":
        return BedrockLLMProvider(
            model_id=settings.bedrock_model_id,
            region_name=settings.bedrock_region,
        )
    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")


def build_default_retriever(knowledge_dir: str | Path = "knowledge") -> KnowledgeRetriever:
    """Build the deterministic local retriever used by local agent orchestration."""
    return build_local_retriever(knowledge_dir)
