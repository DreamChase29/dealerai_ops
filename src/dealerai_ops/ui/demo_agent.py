"""Deterministic agent demo runtime for the Streamlit portfolio UI."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from dealerai_ops.agents.orchestrator import AgentOrchestrator
from dealerai_ops.agents.providers import ScriptedLLMProvider
from dealerai_ops.agents.schemas import (
    AgentRunRequest,
    AgentRunResult,
    ConversationState,
    FinalResponse,
    ModelResponse,
    ToolRequest,
)
from dealerai_ops.domain.enums import AppointmentChannel, AppointmentType
from dealerai_ops.ml.schemas import NoShowPredictionRequest, NoShowPredictionResponse, RiskTier
from dealerai_ops.observability import InMemoryTelemetrySink, set_telemetry_sink
from dealerai_ops.observability.tracing import SpanRecord
from dealerai_ops.rag.retriever import build_local_retriever
from dealerai_ops.tools.executor import ToolExecutor
from dealerai_ops.ui.demo_data import DemoSnapshot


@dataclass(frozen=True)
class DemoAgentTurn:
    """Result and operational trace for one demo assistant turn."""

    result: AgentRunResult
    spans: list[SpanRecord]


class DemoNoShowPredictionService:
    """Deterministic no-show predictor used by the UI's typed tool executor."""

    model_version = "demo-static-no-show-v1"

    def predict(self, request: NoShowPredictionRequest) -> NoShowPredictionResponse:
        """Return a stable probability derived from non-leaky operational features."""
        probability = 0.08
        probability += min(request.prior_no_show_count_at_booking, 4) * 0.04
        probability += max(0, request.lead_time_days - 10) * 0.004
        probability -= min(request.reminder_count, 3) * 0.02
        probability += 0.03 if request.customer_distance_miles > 30 else 0
        probability = round(min(max(probability, 0.01), 0.82), 4)
        return NoShowPredictionResponse(
            probability=probability,
            risk_tier=_risk_tier(probability),
            model_version=self.model_version,
        )


def sample_prompts(snapshot: DemoSnapshot) -> dict[str, str]:
    """Return named deterministic scenarios for the assistant page."""
    return {
        "Customer lookup": f"Look up synthetic customer {snapshot.customer_id}.",
        "Owned vehicle": f"Show vehicle details for {snapshot.vehicle_id}.",
        "Service history": f"Show recent service history for vehicle {snapshot.vehicle_id}.",
        "Inventory search": "Find available Toyota inventory under consideration.",
        "Scheduling policy": "What is the fictional policy for service scheduling changes?",
        "No-show risk": f"Estimate no-show risk for appointment {snapshot.appointment_id}.",
        "Book appointment": "Book the next available maintenance appointment for this customer.",
        "Human escalation": "I want a human advisor to help me with this synthetic account.",
    }


def run_demo_agent_turn(
    snapshot: DemoSnapshot,
    session_factory: sessionmaker[Session],
    user_message: str,
    confirmed: bool = False,
    state: ConversationState | None = None,
) -> DemoAgentTurn:
    """Run one deterministic assistant turn against the production agent stack."""
    sink = InMemoryTelemetrySink()
    set_telemetry_sink(sink)
    request_id = _request_id_for(user_message, confirmed, state)
    with session_factory() as session:
        tool_executor = ToolExecutor(
            session=session,
            no_show_service=DemoNoShowPredictionService(),
        )
        orchestrator = AgentOrchestrator(
            provider=ScriptedLLMProvider(_script_for_message(user_message, snapshot, confirmed)),
            tool_executor=tool_executor,
            retriever=build_local_retriever("knowledge"),
            agent_version="demo-ui-agent-v1",
            prompt_version="demo-ui-prompts-v1",
            model_version="local-scripted-demo-v1",
        )
        result = orchestrator.run(
            AgentRunRequest(
                request_id=request_id,
                conversation_id=snapshot.conversation_id,
                authenticated_customer_id=snapshot.customer_id,
                actor_id="demo_user",
                user_message=user_message,
                confirmed=confirmed,
                state=state,
            )
        )
    return DemoAgentTurn(result=result, spans=list(sink.spans))


def trace_frame_rows(spans: list[SpanRecord]) -> list[dict[str, Any]]:
    """Convert redacted span records into table rows for the Agent Trace page."""
    rows: list[dict[str, Any]] = []
    for span in spans:
        rows.append(
            {
                "event": _event_label(span.name),
                "status": span.status.value,
                "latency_ms": round(span.latency_ms, 2),
                "request_id": span.request_id,
                "conversation_id": span.conversation_id,
                "attributes": span.attributes,
                "error": span.error_type,
            }
        )
    return rows


def _script_for_message(
    user_message: str,
    snapshot: DemoSnapshot,
    confirmed: bool,
) -> list[ModelResponse]:
    lowered = user_message.lower()
    if confirmed:
        return [
            FinalResponse(
                message="Appointment booked successfully using the confirmed tool result."
            )
        ]
    if "book" in lowered or ("appointment" in lowered and "next available" in lowered):
        return [
            ToolRequest(
                tool_name="book_service_appointment",
                arguments={
                    "customer_id": snapshot.customer_id,
                    "vehicle_id": snapshot.vehicle_id,
                    "slot_id": snapshot.slot_id,
                    "appointment_type": AppointmentType.MAINTENANCE.value,
                    "channel": AppointmentChannel.WEB.value,
                    "idempotency_key": _idempotency_key(user_message),
                },
            )
        ]
    if "risk" in lowered or "no-show" in lowered or "no show" in lowered:
        return [
            ToolRequest(
                tool_name="predict_no_show_risk",
                arguments={"appointment_id": snapshot.appointment_id},
            ),
            FinalResponse(
                message=("The no-show risk estimate is available from the prediction tool result.")
            ),
        ]
    if "history" in lowered or "service history" in lowered:
        return [
            ToolRequest(
                tool_name="get_service_history",
                arguments={"vehicle_id": snapshot.vehicle_id, "limit": 8},
            ),
            FinalResponse(message="Recent synthetic service history is shown in the tool result."),
        ]
    if "vehicle" in lowered and "inventory" not in lowered:
        return [
            ToolRequest(
                tool_name="get_vehicle_details",
                arguments={"vehicle_id": snapshot.vehicle_id},
            ),
            FinalResponse(message="Vehicle details are shown in the validated tool result."),
        ]
    if "inventory" in lowered or "stock" in lowered or "available" in lowered:
        return [
            ToolRequest(tool_name="search_inventory", arguments={"make": "Toyota", "limit": 6}),
            FinalResponse(message="Available synthetic inventory matches are shown below."),
        ]
    if "policy" in lowered or "warranty" in lowered or "maintenance" in lowered:
        return [
            FinalResponse(
                message=(
                    "I found relevant synthetic dealership policy sources. The answer is grounded "
                    "in the cited retrieved material."
                )
            )
        ]
    return [
        ToolRequest(
            tool_name="lookup_customer",
            arguments={"customer_id": snapshot.customer_id},
        ),
        FinalResponse(message="Synthetic customer profile returned by the lookup tool."),
    ]


def _event_label(name: str) -> str:
    labels = {
        "conversation": "Conversation",
        "llm_call": "Model call",
        "retrieval_operation": "Retrieval",
        "tool_call": "Tool requested/result",
        "guardrail_decision": "Guardrail decision",
        "human_escalation": "Human escalation",
        "model_inference": "Model inference",
    }
    return labels.get(name, name.replace("_", " ").title())


def _request_id_for(
    user_message: str,
    confirmed: bool,
    state: ConversationState | None,
) -> str:
    state_marker = "pending" if state is not None and state.pending_confirmation else "fresh"
    digest = hashlib.sha256(f"{user_message}:{confirmed}:{state_marker}".encode()).hexdigest()
    return f"ui_req_{digest[:16]}"


def _idempotency_key(user_message: str) -> str:
    digest = hashlib.sha256(user_message.encode()).hexdigest()
    return f"ui-book-{digest[:16]}"


def _risk_tier(probability: float) -> RiskTier:
    if probability >= 0.55:
        return RiskTier.VERY_HIGH
    if probability >= 0.35:
        return RiskTier.HIGH
    if probability >= 0.18:
        return RiskTier.MEDIUM
    return RiskTier.LOW
