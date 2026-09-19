"""Optional Amazon Bedrock LLM provider adapter."""

import json
from collections.abc import Sequence
from typing import Any, cast

from pydantic import TypeAdapter, ValidationError

from dealerai_ops.agents.providers import LLMProviderError
from dealerai_ops.agents.schemas import ConversationState, ModelResponse
from dealerai_ops.rag.schemas import RetrievedChunk

ModelResponseAdapter: TypeAdapter[ModelResponse] = TypeAdapter(ModelResponse)


class BedrockLLMProvider:
    """Amazon Bedrock adapter for future AWS-backed structured model responses."""

    def __init__(
        self,
        model_id: str,
        region_name: str,
        client: Any | None = None,
    ) -> None:
        self.model_id = model_id
        self.region_name = region_name
        self.client = client or self._build_client(region_name)

    def next_response(
        self,
        state: ConversationState,
        retrieved_chunks: Sequence[RetrievedChunk],
        tool_metadata: list[dict[str, object]],
    ) -> ModelResponse:
        """Request a structured JSON response from Bedrock."""
        prompt = {
            "instruction": (
                "Return only JSON matching one of: "
                "{type:'tool_request', tool_name:string, arguments:object} or "
                "{type:'final', message:string}. Never invent tool success."
            ),
            "messages": [message.model_dump(mode="json") for message in state.messages],
            "retrieved_chunks": [chunk.model_dump(mode="json") for chunk in retrieved_chunks],
            "tools": tool_metadata,
        }
        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(prompt).encode("utf-8"),
                contentType="application/json",
                accept="application/json",
            )
            body = response["body"].read().decode("utf-8")
            payload = json.loads(body)
            if "completion" in payload and isinstance(payload["completion"], str):
                payload = json.loads(payload["completion"])
            return ModelResponseAdapter.validate_python(payload)
        except (KeyError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise LLMProviderError(f"Bedrock returned invalid structured output: {exc}") from exc
        except Exception as exc:
            raise LLMProviderError(f"Bedrock invocation failed: {exc}") from exc

    @staticmethod
    def _build_client(region_name: str) -> Any:
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError as exc:
            raise LLMProviderError("boto3 is not installed; Bedrock provider is optional.") from exc
        return cast(Any, boto3.client("bedrock-runtime", region_name=region_name))
