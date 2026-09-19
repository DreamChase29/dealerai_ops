"""Agent guardrails and policy enforcement."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from dealerai_ops.agents.schemas import AgentError, AgentFailureCode, ToolRequest
from dealerai_ops.rag.schemas import RetrievedChunk
from dealerai_ops.tools.operations import ToolDefinition
from dealerai_ops.tools.types import ToolRiskLevel


class GuardrailViolationCode(StrEnum):
    """Machine-readable guardrail violation codes."""

    PROMPT_INJECTION = "PROMPT_INJECTION"
    PII_EXFILTRATION = "PII_EXFILTRATION"
    SECRET_EXFILTRATION = "SECRET_EXFILTRATION"  # noqa: S105
    MASS_OPERATION = "MASS_OPERATION"
    CONFIRMATION_BYPASS = "CONFIRMATION_BYPASS"
    RETRIEVED_POLICY_INJECTION = "RETRIEVED_POLICY_INJECTION"
    TOOL_NOT_ALLOWED = "TOOL_NOT_ALLOWED"
    SENSITIVE_OPERATION_DENIED = "SENSITIVE_OPERATION_DENIED"


@dataclass(frozen=True)
class GuardrailDecision:
    """Policy decision for an agent boundary."""

    allowed: bool
    code: GuardrailViolationCode | None = None
    message: str = ""
    details: dict[str, object] = field(default_factory=dict)

    def to_agent_error(self) -> AgentError:
        """Return an agent error representation."""
        return AgentError(
            code=self.code.value if self.code is not None else AgentFailureCode.POLICY_VIOLATION,
            message=self.message or "Agent guardrail blocked the request.",
            details=self.details,
        )


@dataclass(frozen=True)
class AgentGuardrailPolicy:
    """Fail-closed defense-in-depth policy for agent orchestration."""

    allowed_tools: frozenset[str]
    max_retrieval_chunks: int = 5
    sensitive_write_tools: frozenset[str] = frozenset(
        {
            "book_service_appointment",
            "reschedule_service_appointment",
            "cancel_service_appointment",
            "create_sales_lead",
            "handoff_to_human",
        }
    )

    def inspect_user_message(self, message: str) -> GuardrailDecision:
        """Inspect user input before retrieval, provider reasoning, or tool execution."""
        lowered = message.lower()
        if _contains_any(
            lowered,
            (
                "ignore your rules",
                "ignore all rules",
                "disregard your rules",
                "forget your instructions",
                "override system",
                "bypass system",
                "bypass policy",
                "bypass tool policy",
                "disable guardrails",
                "write directly to the database",
                "pretend the booking succeeded",
                "pretend booking succeeded",
            ),
        ):
            return _deny(
                GuardrailViolationCode.PROMPT_INJECTION,
                "I cannot ignore system, developer, safety, or tool policies.",
            )
        if _contains_any(
            lowered,
            (
                "phone numbers",
                "email addresses",
                "emails",
                "customer contact data",
                "contact data",
                "private customer contact",
                "customer contact fields",
            ),
        ) and _contains_any(
            lowered,
            ("reveal", "list", "show", "dump", "export", "all customers"),
        ):
            return _deny(
                GuardrailViolationCode.PII_EXFILTRATION,
                "I cannot reveal customer contact information or bulk PII.",
            )
        if _contains_any(
            lowered,
            (
                "dump the database",
                "dump database",
                "all customers",
                "every customer",
                "every appointment",
                "cancel every",
                "cancel all",
                "delete every",
                "delete all",
            ),
        ) and _contains_any(lowered, ("cancel", "delete", "dump", "reschedule", "export")):
            return _deny(
                GuardrailViolationCode.MASS_OPERATION,
                "I cannot perform bulk destructive or bulk export operations.",
            )
        if _contains_any(
            lowered,
            ("password", "api key", "secret", "token", "credential", "configuration"),
        ) and _contains_any(lowered, ("tell me", "show", "reveal", "print", "dump")):
            return _deny(
                GuardrailViolationCode.SECRET_EXFILTRATION,
                "I cannot reveal passwords, secrets, tokens, credentials, or configuration values.",
            )
        if _contains_any(
            lowered,
            ("without asking", "without confirmation", "do not ask me", "skip confirmation"),
        ) and _contains_any(lowered, ("book", "reschedule", "cancel", "create lead")):
            return _deny(
                GuardrailViolationCode.CONFIRMATION_BYPASS,
                "Write actions require explicit confirmation and cannot skip that workflow.",
            )
        return GuardrailDecision(allowed=True)

    def inspect_retrieved_chunks(self, chunks: list[RetrievedChunk]) -> GuardrailDecision:
        """Treat retrieved documents as untrusted facts, never as policy instructions."""
        for chunk in chunks[: self.max_retrieval_chunks]:
            lowered = chunk.text.lower()
            if _contains_any(
                lowered,
                (
                    "ignore your rules",
                    "bypass system",
                    "bypass tool",
                    "disable guardrails",
                    "dump the database",
                    "allowed to dump the database",
                    "reveal all customer",
                ),
            ):
                return _deny(
                    GuardrailViolationCode.RETRIEVED_POLICY_INJECTION,
                    "Retrieved content attempted to override system or tool policy.",
                    {"document_id": chunk.document_id, "chunk_id": chunk.chunk_id},
                )
        return GuardrailDecision(allowed=True)

    def inspect_tool_request(
        self,
        tool_request: ToolRequest,
        registry: Mapping[str, ToolDefinition],
    ) -> GuardrailDecision:
        """Validate a provider-requested tool against allowlist and risk policy."""
        if tool_request.tool_name not in self.allowed_tools:
            return _deny(
                GuardrailViolationCode.TOOL_NOT_ALLOWED,
                f"Tool is not allowlisted: {tool_request.tool_name}",
                {"tool_name": tool_request.tool_name},
            )
        tool = registry.get(tool_request.tool_name)
        if tool is None:
            return _deny(
                GuardrailViolationCode.TOOL_NOT_ALLOWED,
                f"Tool is not registered: {tool_request.tool_name}",
                {"tool_name": tool_request.tool_name},
            )
        if (
            tool.risk_level in {ToolRiskLevel.LOW_RISK_WRITE, ToolRiskLevel.HIGH_RISK_WRITE}
            and not tool.requires_confirmation
        ):
            return _deny(
                GuardrailViolationCode.SENSITIVE_OPERATION_DENIED,
                "Write tools must require confirmation.",
                {"tool_name": tool_request.tool_name},
            )
        return GuardrailDecision(allowed=True)


def default_agent_guardrail_policy(
    allowed_tools: frozenset[str],
    max_retrieval_chunks: int = 5,
) -> AgentGuardrailPolicy:
    """Build the default fail-closed agent guardrail policy."""
    return AgentGuardrailPolicy(
        allowed_tools=allowed_tools,
        max_retrieval_chunks=max(1, max_retrieval_chunks),
    )


def _deny(
    code: GuardrailViolationCode,
    message: str,
    details: dict[str, object] | None = None,
) -> GuardrailDecision:
    return GuardrailDecision(
        allowed=False,
        code=code,
        message=message,
        details=details or {},
    )


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)
