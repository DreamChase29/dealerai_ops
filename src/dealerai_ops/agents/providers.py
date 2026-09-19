"""Provider-independent LLM interfaces and local deterministic providers."""

from collections.abc import Sequence
from typing import Protocol

from dealerai_ops.agents.schemas import ConversationState, FinalResponse, ModelResponse, ToolRequest
from dealerai_ops.rag.schemas import RetrievedChunk
from dealerai_ops.tools.types import ToolExecutionOutcome


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider cannot return a structured response."""


class LLMProvider(Protocol):
    """Provider-independent interface for structured model responses."""

    def next_response(
        self,
        state: ConversationState,
        retrieved_chunks: Sequence[RetrievedChunk],
        tool_metadata: list[dict[str, object]],
    ) -> ModelResponse:
        """Return the next structured model response."""


class ScriptedLLMProvider:
    """Deterministic local provider that returns scripted structured responses."""

    def __init__(self, responses: Sequence[ModelResponse]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def next_response(
        self,
        state: ConversationState,
        retrieved_chunks: Sequence[RetrievedChunk],
        tool_metadata: list[dict[str, object]],
    ) -> ModelResponse:
        """Return the next scripted response."""
        if self.calls >= len(self._responses):
            return FinalResponse(message="I do not have another deterministic response scripted.")
        response = self._responses[self.calls]
        self.calls += 1
        return response


class RuleBasedLocalLLMProvider:
    """Simple deterministic local provider for offline demos and tests."""

    def next_response(
        self,
        state: ConversationState,
        retrieved_chunks: Sequence[RetrievedChunk],
        tool_metadata: list[dict[str, object]],
    ) -> ModelResponse:
        """Choose a basic structured response from current conversation state."""
        if state.tool_results:
            latest = state.tool_results[-1]
            if latest.outcome == ToolExecutionOutcome.SUCCEEDED:
                return FinalResponse(message=f"Tool `{latest.tool_name}` completed successfully.")
            if latest.outcome == ToolExecutionOutcome.REQUIRES_CONFIRMATION:
                return FinalResponse(
                    message=f"Tool `{latest.tool_name}` requires explicit confirmation."
                )
            return FinalResponse(message=f"Tool `{latest.tool_name}` failed: {latest.error}")

        user_message = state.messages[-1].content.lower() if state.messages else ""
        if "customer" in user_message and "cus_" in user_message:
            customer_id = _first_token_with_prefix(user_message, "cus_")
            return ToolRequest(tool_name="lookup_customer", arguments={"customer_id": customer_id})
        if retrieved_chunks:
            citation = retrieved_chunks[0]
            return FinalResponse(
                message=(
                    f"According to {citation.title}, section {citation.section} "
                    f"({citation.document_id}/{citation.chunk_id}): {citation.text}"
                )
            )
        return FinalResponse(message="I can help with synthetic dealership operations.")


class FailingLLMProvider:
    """Deterministic provider used to exercise provider-failure handling."""

    def __init__(self, message: str = "provider unavailable") -> None:
        self.message = message

    def next_response(
        self,
        state: ConversationState,
        retrieved_chunks: Sequence[RetrievedChunk],
        tool_metadata: list[dict[str, object]],
    ) -> ModelResponse:
        """Raise a provider error."""
        raise LLMProviderError(self.message)


def _first_token_with_prefix(text: str, prefix: str) -> str:
    for token in text.replace(",", " ").replace(".", " ").split():
        if token.startswith(prefix):
            return token
    return ""
