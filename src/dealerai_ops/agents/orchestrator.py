"""LLM-independent agent orchestration loop."""

from time import monotonic
from typing import Any

import structlog

from dealerai_ops.agents.guardrails import (
    AgentGuardrailPolicy,
    GuardrailDecision,
    GuardrailViolationCode,
    default_agent_guardrail_policy,
)
from dealerai_ops.agents.providers import LLMProvider, LLMProviderError
from dealerai_ops.agents.schemas import (
    AgentError,
    AgentFailureCode,
    AgentMessage,
    AgentRole,
    AgentRunRequest,
    AgentRunResult,
    AgentStatus,
    ConversationState,
    FinalResponse,
    ToolRequest,
)
from dealerai_ops.core.config import get_settings
from dealerai_ops.domain.enums import EscalationReason
from dealerai_ops.escalations.service import EscalationService
from dealerai_ops.observability import start_span
from dealerai_ops.rag.retriever import KnowledgeRetriever, citations_from_chunks
from dealerai_ops.tools.executor import ToolExecutor
from dealerai_ops.tools.types import ToolCallResult, ToolContext, ToolExecutionOutcome

logger = structlog.get_logger(__name__)

TRANSACTIONAL_SUCCESS_TERMS = {
    "booked",
    "booking succeeded",
    "rescheduled",
    "canceled",
    "cancelled",
    "lead created",
    "escalated",
}
TRANSACTIONAL_TOOLS = {
    "book_service_appointment",
    "reschedule_service_appointment",
    "cancel_service_appointment",
    "create_sales_lead",
    "handoff_to_human",
}
RETRIEVAL_HINTS = {
    "policy",
    "warranty",
    "maintenance",
    "recall",
    "privacy",
    "scheduling",
    "hours",
    "faq",
    "inventory terminology",
    "escalation",
}
CUSTOMER_ESCALATION_HINTS = {
    "human",
    "representative",
    "manager",
    "advisor",
    "person",
    "call me",
}
IDENTITY_AMBIGUITY_HINTS = {
    "not sure who i am",
    "which customer",
    "multiple customers",
    "wrong customer",
    "identity unclear",
    "identity is unclear",
}


class AgentOrchestrator:
    """Coordinate retrieval, model reasoning, typed tool execution, and final response."""

    def __init__(
        self,
        provider: LLMProvider,
        tool_executor: ToolExecutor,
        retriever: KnowledgeRetriever | None = None,
        max_tool_iterations: int = 4,
        timeout_seconds: float = 10.0,
        tool_timeout_seconds: float = 5.0,
        guardrail_policy: AgentGuardrailPolicy | None = None,
        escalation_service: EscalationService | None = None,
        agent_version: str | None = None,
        prompt_version: str | None = None,
        model_version: str | None = None,
    ) -> None:
        settings = get_settings()
        self.provider = provider
        self.tool_executor = tool_executor
        self.retriever = retriever
        self.max_tool_iterations = max_tool_iterations
        self.timeout_seconds = timeout_seconds
        self.tool_timeout_seconds = tool_timeout_seconds
        self.guardrail_policy = guardrail_policy or default_agent_guardrail_policy(
            allowed_tools=frozenset(tool_executor.registry)
        )
        self.escalation_service = escalation_service or EscalationService(tool_executor.session)
        self.agent_version = agent_version or settings.agent_version
        self.prompt_version = prompt_version or settings.prompt_version
        self.model_version = model_version or settings.llm_model_version

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        """Run the agent loop for one user turn with conversation-level telemetry."""
        with start_span(
            "conversation",
            attributes={
                "agent_version": self.agent_version,
                "prompt_version": self.prompt_version,
                "model_version": self.model_version,
                "confirmed": request.confirmed,
            },
            correlation_id=request.request_id,
            request_id=request.request_id,
            conversation_id=request.conversation_id,
        ) as span:
            result = self._run_inner(request)
            span.set_attributes(
                {
                    "status": result.status.value,
                    "model_calls": result.state.iteration_count
                    + (1 if result.final_answer is not None else 0),
                    "tool_calls": len(result.state.tool_results),
                    "retrieval_count": len(result.state.retrieved_chunks),
                    "error_code": result.error.code if result.error is not None else None,
                }
            )
            if result.error is not None:
                span.mark_error(result.error.message, str(result.error.code))
            return result

    def _run_inner(self, request: AgentRunRequest) -> AgentRunResult:
        """Run the agent loop for one user turn."""
        started_at = monotonic()
        state = request.state or ConversationState(conversation_id=request.conversation_id)
        intent = _infer_intent(request.user_message)
        state.messages.append(
            AgentMessage(
                role=AgentRole.USER,
                content=request.user_message,
                metadata={"intent": intent},
            )
        )

        with start_span(
            "guardrail_decision",
            attributes={"boundary": "user_message"},
        ) as span:
            user_decision = self.guardrail_policy.inspect_user_message(request.user_message)
            span.set_attributes(
                {
                    "allowed": user_decision.allowed,
                    "code": user_decision.code.value if user_decision.code else None,
                }
            )
        if not user_decision.allowed:
            return self._policy_failure(request, state, user_decision)

        if _is_identity_ambiguous(request.user_message):
            return self._escalate(
                request=request,
                state=state,
                reason=EscalationReason.IDENTITY_AMBIGUITY,
                recommended_next_action=(
                    "Verify the customer's identity before sharing account-specific information."
                ),
            )

        if _requests_human_escalation(request.user_message):
            return self._escalate(
                request=request,
                state=state,
                reason=EscalationReason.CUSTOMER_REQUEST,
                recommended_next_action=(
                    "Have a dealership team member review the conversation and contact the "
                    "customer."
                ),
            )

        if self.retriever is not None and _should_retrieve(request.user_message):
            try:
                state.retrieved_chunks = self.retriever.retrieve(
                    request.user_message,
                    top_k=self.guardrail_policy.max_retrieval_chunks,
                )
            except (RuntimeError, TimeoutError) as exc:
                return self._escalate(
                    request,
                    state,
                    EscalationReason.LOW_CONFIDENCE,
                    "Review retrieval availability and answer the knowledge request manually.",
                    AgentError(code=AgentFailureCode.RETRIEVAL_FAILURE, message=str(exc)),
                )
            with start_span(
                "guardrail_decision",
                attributes={"boundary": "retrieved_chunks"},
            ) as span:
                retrieval_decision = self.guardrail_policy.inspect_retrieved_chunks(
                    state.retrieved_chunks
                )
                span.set_attributes(
                    {
                        "allowed": retrieval_decision.allowed,
                        "code": retrieval_decision.code.value if retrieval_decision.code else None,
                    }
                )
            if not retrieval_decision.allowed:
                return self._policy_failure(request, state, retrieval_decision)

        if request.confirmed and state.pending_confirmation is not None:
            confirmed_request = state.pending_confirmation.model_copy(deep=True)
            confirmed_request.arguments["confirmed"] = True
            state.pending_confirmation = None
            tool_result = self._execute_tool(confirmed_request, request, state, started_at)
            if tool_result is None:
                return self._failure(
                    request,
                    state,
                    AgentFailureCode.TOOL_TIMEOUT,
                    "Tool execution exceeded timeout.",
                )
            state.tool_results.append(tool_result)
            state.messages.append(
                AgentMessage(
                    role=AgentRole.TOOL,
                    content=tool_result.model_dump_json(),
                    metadata={"tool_name": tool_result.tool_name},
                )
            )
            tool_escalation_reason = self._tool_escalation_reason(state, tool_result)
            if tool_escalation_reason is not None:
                return self._escalate(
                    request=request,
                    state=state,
                    reason=tool_escalation_reason,
                    recommended_next_action=(
                        "Review the failed confirmed tool call and resolve the request manually."
                    ),
                )

        while state.iteration_count < self.max_tool_iterations:
            if monotonic() - started_at > self.timeout_seconds:
                return self._failure(
                    request,
                    state,
                    AgentFailureCode.TOOL_TIMEOUT,
                    "Agent run exceeded timeout.",
                )

            try:
                with start_span(
                    "llm_call",
                    attributes={
                        "agent_version": self.agent_version,
                        "prompt_version": self.prompt_version,
                        "model_version": self.model_version,
                        "iteration": state.iteration_count + 1,
                    },
                ) as span:
                    model_response = self.provider.next_response(
                        state=state,
                        retrieved_chunks=state.retrieved_chunks,
                        tool_metadata=self._allowed_tool_metadata(),
                    )
                    span.set_attribute("response_type", model_response.type)
            except LLMProviderError as exc:
                return self._escalate(
                    request,
                    state,
                    EscalationReason.LOW_CONFIDENCE,
                    "Review provider availability and continue the conversation manually.",
                    AgentError(code=AgentFailureCode.PROVIDER_FAILURE, message=str(exc)),
                )
            except TimeoutError as exc:
                return self._escalate(
                    request,
                    state,
                    EscalationReason.LOW_CONFIDENCE,
                    "Review provider latency and continue the conversation manually.",
                    AgentError(code=AgentFailureCode.PROVIDER_TIMEOUT, message=str(exc)),
                )

            if isinstance(model_response, FinalResponse):
                if _fabricates_transaction_success(model_response.message, state):
                    return self._escalate(
                        request=request,
                        state=state,
                        reason=EscalationReason.SAFETY_CONCERN,
                        recommended_next_action=(
                            "Review the conversation because the model attempted to claim "
                            "transactional success without tool confirmation."
                        ),
                        error=AgentError(
                            code=AgentFailureCode.INVALID_MODEL_OUTPUT,
                            message=(
                                "Model claimed transactional success without a successful tool "
                                "result."
                            ),
                        ),
                    )
                state.messages.append(
                    AgentMessage(role=AgentRole.ASSISTANT, content=model_response.message)
                )
                return AgentRunResult(
                    request_id=request.request_id,
                    conversation_id=request.conversation_id,
                    status=AgentStatus.COMPLETED,
                    final_answer=model_response.message,
                    state=state,
                    citations=citations_from_chunks(state.retrieved_chunks),
                )

            tool_request = model_response
            if tool_request.tool_name not in self.tool_executor.registry:
                return self._failure(
                    request,
                    state,
                    AgentFailureCode.UNKNOWN_TOOL,
                    f"Model requested an unknown tool: {tool_request.tool_name}",
                    details={"tool_name": tool_request.tool_name},
                )

            with start_span(
                "guardrail_decision",
                attributes={"boundary": "tool_request", "tool_name": tool_request.tool_name},
            ) as span:
                tool_decision = self.guardrail_policy.inspect_tool_request(
                    tool_request,
                    self.tool_executor.registry,
                )
                span.set_attributes(
                    {
                        "allowed": tool_decision.allowed,
                        "code": tool_decision.code.value if tool_decision.code else None,
                    }
                )
            if not tool_decision.allowed:
                return self._policy_failure(request, state, tool_decision)

            tool_request = self._prepare_unconfirmed_tool_request(tool_request)
            state.iteration_count += 1
            tool_result = self._execute_tool(tool_request, request, state, started_at)
            if tool_result is None:
                return self._failure(
                    request,
                    state,
                    AgentFailureCode.TOOL_TIMEOUT,
                    "Tool execution exceeded timeout.",
                )
            state.tool_results.append(tool_result)
            state.messages.append(
                AgentMessage(
                    role=AgentRole.TOOL,
                    content=tool_result.model_dump_json(),
                    metadata={"tool_name": tool_result.tool_name},
                )
            )

            if tool_result.outcome == ToolExecutionOutcome.REQUIRES_CONFIRMATION:
                state.pending_confirmation = tool_request
                return AgentRunResult(
                    request_id=request.request_id,
                    conversation_id=request.conversation_id,
                    status=AgentStatus.REQUIRES_CONFIRMATION,
                    final_answer=(
                        "This action requires explicit confirmation before I can continue."
                    ),
                    state=state,
                    error=AgentError(
                        code="CONFIRMATION_REQUIRED",
                        message="Tool requires confirmation.",
                    ),
                )

            tool_escalation_reason = self._tool_escalation_reason(state, tool_result)
            if tool_escalation_reason is not None:
                return self._escalate(
                    request=request,
                    state=state,
                    reason=tool_escalation_reason,
                    recommended_next_action=(
                        "Review the failed tool call and resolve the customer's request manually."
                    ),
                )

        return self._failure(
            request,
            state,
            AgentFailureCode.ITERATION_LIMIT,
            "Maximum tool iteration limit reached.",
            details={"max_tool_iterations": self.max_tool_iterations},
        )

    def _allowed_tool_metadata(self) -> list[dict[str, Any]]:
        return [
            tool
            for tool in self.tool_executor.metadata()
            if isinstance(tool.get("name"), str)
            and str(tool["name"]) in self.guardrail_policy.allowed_tools
        ]

    def _prepare_unconfirmed_tool_request(self, tool_request: ToolRequest) -> ToolRequest:
        tool = self.tool_executor.registry[tool_request.tool_name]
        if not tool.requires_confirmation:
            return tool_request
        guarded_request = tool_request.model_copy(deep=True)
        guarded_request.arguments["confirmed"] = False
        return guarded_request

    def _execute_tool(
        self,
        tool_request: ToolRequest,
        request: AgentRunRequest,
        state: ConversationState,
        started_at: float,
    ) -> ToolCallResult | None:
        before = monotonic()
        tool_sequence = len(state.tool_results) + 1
        result = self.tool_executor.execute(
            tool_request.tool_name,
            tool_request.arguments,
            ToolContext(
                request_id=f"{request.request_id}:tool:{tool_sequence}",
                actor_id=request.actor_id,
                conversation_id=request.conversation_id,
            ),
        )
        elapsed = monotonic() - before
        if elapsed > self.tool_timeout_seconds or monotonic() - started_at > self.timeout_seconds:
            return None
        return result

    def _tool_escalation_reason(
        self,
        state: ConversationState,
        tool_result: ToolCallResult,
    ) -> EscalationReason | None:
        if tool_result.outcome not in {
            ToolExecutionOutcome.FAILED,
            ToolExecutionOutcome.UNAUTHORIZED,
        }:
            return None
        failed_results = [
            result
            for result in state.tool_results
            if result.outcome in {ToolExecutionOutcome.FAILED, ToolExecutionOutcome.UNAUTHORIZED}
        ]
        if len(failed_results) >= 2:
            return EscalationReason.REPEATED_FAILURE
        tool = self.tool_executor.registry.get(tool_result.tool_name)
        if tool is None:
            return None
        if tool.name in self.guardrail_policy.sensitive_write_tools:
            return EscalationReason.TOOL_FAILURE
        return None

    def _escalate(
        self,
        request: AgentRunRequest,
        state: ConversationState,
        reason: EscalationReason,
        recommended_next_action: str,
        error: AgentError | None = None,
    ) -> AgentRunResult:
        with start_span(
            "human_escalation",
            attributes={"reason": reason.value},
            correlation_id=request.request_id,
            request_id=request.request_id,
            conversation_id=request.conversation_id,
        ) as span:
            record = self.escalation_service.create_escalation_package(
                request_id=request.request_id,
                conversation_id=request.conversation_id,
                reason=reason,
                state=state,
                recommended_next_action=recommended_next_action,
                authenticated_customer_id=request.authenticated_customer_id,
            )
            span.set_attribute("escalation_id", record.id)
        response = _customer_escalation_response(reason)
        state.messages.append(AgentMessage(role=AgentRole.ASSISTANT, content=response))
        logger.info(
            "agent_escalated",
            request_id=request.request_id,
            escalation_id=record.id,
            reason=reason.value,
        )
        return AgentRunResult(
            request_id=request.request_id,
            conversation_id=request.conversation_id,
            status=AgentStatus.ESCALATED,
            final_answer=response,
            state=state,
            error=error,
            escalation_id=record.id,
            escalation_package=record.package,
            citations=citations_from_chunks(state.retrieved_chunks),
        )

    def _policy_failure(
        self,
        request: AgentRunRequest,
        state: ConversationState,
        decision: GuardrailDecision,
    ) -> AgentRunResult:
        logger.warning(
            "agent_policy_blocked",
            request_id=request.request_id,
            code=decision.code,
            message=decision.message,
            details=decision.details,
        )
        return self._escalate(
            request=request,
            state=state,
            reason=_policy_escalation_reason(decision),
            recommended_next_action=_policy_recommended_next_action(decision),
            error=decision.to_agent_error(),
        )

    @staticmethod
    def _failure(
        request: AgentRunRequest,
        state: ConversationState,
        code: AgentFailureCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> AgentRunResult:
        logger.warning(
            "agent_run_failed", request_id=request.request_id, code=code, message=message
        )
        return AgentRunResult(
            request_id=request.request_id,
            conversation_id=request.conversation_id,
            status=AgentStatus.FAILED,
            state=state,
            error=AgentError(code=code, message=message, details=details or {}),
        )


def _should_retrieve(user_message: str) -> bool:
    lowered = user_message.lower()
    return any(hint in lowered for hint in RETRIEVAL_HINTS)


def _requests_human_escalation(user_message: str) -> bool:
    lowered = user_message.lower()
    return any(hint in lowered for hint in CUSTOMER_ESCALATION_HINTS)


def _is_identity_ambiguous(user_message: str) -> bool:
    lowered = user_message.lower()
    return any(hint in lowered for hint in IDENTITY_AMBIGUITY_HINTS)


def _policy_escalation_reason(decision: GuardrailDecision) -> EscalationReason:
    if decision.code in {
        GuardrailViolationCode.PII_EXFILTRATION,
        GuardrailViolationCode.SECRET_EXFILTRATION,
    }:
        return EscalationReason.SENSITIVE_REQUEST
    if decision.code == GuardrailViolationCode.PROMPT_INJECTION:
        return EscalationReason.SAFETY_CONCERN
    return EscalationReason.POLICY_RESTRICTION


def _policy_recommended_next_action(decision: GuardrailDecision) -> str:
    if decision.code in {
        GuardrailViolationCode.PII_EXFILTRATION,
        GuardrailViolationCode.SECRET_EXFILTRATION,
    }:
        return (
            "Review the sensitive request and respond using approved privacy and security policy."
        )
    if decision.code == GuardrailViolationCode.PROMPT_INJECTION:
        return "Review the safety concern and continue only within approved dealership policies."
    return (
        "Review the policy restriction and decide whether a human-approved alternative is "
        "available."
    )


def _customer_escalation_response(reason: EscalationReason) -> str:
    if reason == EscalationReason.CUSTOMER_REQUEST:
        return "I have routed this to a dealership team member who can help from here."
    if reason == EscalationReason.IDENTITY_AMBIGUITY:
        return (
            "I need a dealership team member to verify the account before continuing with "
            "customer-specific help."
        )
    if reason == EscalationReason.SENSITIVE_REQUEST:
        return (
            "I cannot provide that information here, so I have routed the request for human review."
        )
    if reason == EscalationReason.POLICY_RESTRICTION:
        return (
            "I cannot complete that request under current policy, so I have routed it for review."
        )
    if reason == EscalationReason.TOOL_FAILURE:
        return (
            "I could not complete that action automatically, so I have routed it to a human team."
        )
    if reason == EscalationReason.REPEATED_FAILURE:
        return (
            "I am having repeated trouble completing this automatically, so I have routed it to "
            "a human team."
        )
    if reason == EscalationReason.LOW_CONFIDENCE:
        return (
            "I am not confident I can handle this automatically right now, so I have routed it "
            "to a human team."
        )
    return "I have routed this conversation to a human team member for review."


def _infer_intent(user_message: str) -> str:
    lowered = user_message.lower()
    if any(term in lowered for term in ("book", "schedule appointment", "reserve")):
        return "book_service"
    if any(term in lowered for term in ("reschedule", "move appointment")):
        return "reschedule_service"
    if any(term in lowered for term in ("cancel", "cancel appointment")):
        return "cancel_service"
    if any(term in lowered for term in ("inventory", "stock", "vehicle for sale")):
        return "inventory_search"
    if _should_retrieve(user_message):
        return "knowledge_question"
    if "customer" in lowered:
        return "customer_lookup"
    return "general"


def _fabricates_transaction_success(message: str, state: ConversationState) -> bool:
    lowered = message.lower()
    if not any(term in lowered for term in TRANSACTIONAL_SUCCESS_TERMS):
        return False
    for result in reversed(state.tool_results):
        if result.tool_name in TRANSACTIONAL_TOOLS:
            return result.outcome != ToolExecutionOutcome.SUCCEEDED
    return True
