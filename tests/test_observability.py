"""Tests for observability tracing and redaction."""

from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from dealerai_ops.agents.orchestrator import AgentOrchestrator
from dealerai_ops.agents.providers import ScriptedLLMProvider
from dealerai_ops.agents.schemas import AgentRunRequest, FinalResponse
from dealerai_ops.core.config import Settings
from dealerai_ops.core.redaction import REDACTION
from dealerai_ops.ml.schemas import NoShowPredictionRequest
from dealerai_ops.ml.service import NoShowPredictionService
from dealerai_ops.ml.training import NoShowModelArtifact
from dealerai_ops.observability import InMemoryTelemetrySink, configure_observability
from dealerai_ops.observability.tracing import set_telemetry_sink, start_span
from dealerai_ops.rag.retriever import build_local_retriever
from dealerai_ops.tools.executor import ToolExecutor
from dealerai_ops.tools.types import ToolContext, ToolExecutionOutcome


def test_span_attributes_are_redacted_before_recording() -> None:
    """Telemetry sinks receive redacted values."""
    sink = InMemoryTelemetrySink()
    set_telemetry_sink(sink)

    with start_span(
        "redaction_test",
        attributes={
            "email": "alex@example.com",
            "message": "Call 555-222-1212 password=hunter2",
        },
        correlation_id="corr_1",
    ):
        pass

    span = sink.spans[0]
    assert span.correlation_id == "corr_1"
    assert span.attributes["email"] == REDACTION
    assert REDACTION in str(span.attributes["message"])


def test_agent_run_emits_correlated_conversation_llm_and_retrieval_spans(
    session: Session,
) -> None:
    """Agent runs emit correlated spans for major orchestration boundaries."""
    sink = InMemoryTelemetrySink()
    set_telemetry_sink(sink)
    orchestrator = AgentOrchestrator(
        provider=ScriptedLLMProvider([FinalResponse(message="Grounded answer.")]),
        tool_executor=ToolExecutor(session),
        retriever=build_local_retriever("knowledge"),
        agent_version="agent-test-v1",
        prompt_version="prompt-test-v1",
        model_version="model-test-v1",
    )

    result = orchestrator.run(
        AgentRunRequest(
            request_id="obs-agent-0001",
            conversation_id="conv_obs_0001",
            user_message="What is the service scheduling policy?",
        )
    )

    span_names = [span.name for span in sink.spans]
    assert result.final_answer == "Grounded answer."
    assert "conversation" in span_names
    assert "guardrail_decision" in span_names
    assert "retrieval_operation" in span_names
    assert "llm_call" in span_names
    assert all(span.correlation_id == "obs-agent-0001" for span in sink.spans)


def test_tool_executor_emits_tool_span_on_validation_failure(session: Session) -> None:
    """Tool spans include deterministic outcome and error metadata."""
    sink = InMemoryTelemetrySink()
    set_telemetry_sink(sink)
    executor = ToolExecutor(session)

    result = executor.execute(
        "lookup_customer",
        {"unexpected": True},
        ToolContext(request_id="obs-tool-0001", conversation_id=None),
    )

    span = next(record for record in sink.spans if record.name == "tool_call")
    assert result.outcome == ToolExecutionOutcome.FAILED
    assert span.status == "error"
    assert span.attributes["tool_name"] == "lookup_customer"
    assert span.attributes["error_code"] == "VALIDATION_ERROR"


def test_no_show_prediction_emits_model_inference_span() -> None:
    """Prediction service emits latency and model-version telemetry."""
    sink = InMemoryTelemetrySink()
    set_telemetry_sink(sink)
    service = NoShowPredictionService(
        NoShowModelArtifact(
            model=_FakeProbabilityModel(),
            feature_schema={},
            metadata={"model_version": "obs-no-show-v1"},
            metrics={},
        )
    )

    response = service.predict(_sample_request())

    span = next(record for record in sink.spans if record.name == "model_inference")
    assert response.model_version == "obs-no-show-v1"
    assert span.attributes["model_version"] == "obs-no-show-v1"
    assert span.attributes["risk_tier"] == response.risk_tier.value
    assert span.latency_ms >= 0


def test_mlflow_observability_can_be_enabled_without_installed_package() -> None:
    """Optional MLflow mode degrades to structured logging when MLflow is absent."""
    configure_observability(
        Settings(
            observability_enabled=False,
            mlflow_enabled=True,
            mlflow_tracking_uri="file:work/mlruns-test",
        )
    )
    sink = InMemoryTelemetrySink()
    set_telemetry_sink(sink)

    with start_span("after_mlflow_config"):
        pass

    assert sink.spans[0].name == "after_mlflow_config"


class _FakeProbabilityModel:
    def predict_proba(self, features: Any) -> np.ndarray:
        del features
        return np.array([[0.7, 0.3]])


def _sample_request() -> NoShowPredictionRequest:
    return NoShowPredictionRequest(
        appointment_type="maintenance",
        channel="web",
        lead_time_days=21,
        estimated_duration_minutes=75,
        is_first_service_visit=False,
        prior_no_show_count_at_booking=1,
        prior_completed_appointments_at_booking=2,
        reminder_count=1,
        scheduled_day_of_week=2,
        scheduled_hour=9,
        days_since_customer_created_at_booking=400,
        vehicle_age_years_at_booking=4,
        customer_distance_miles=24.5,
        customer_loyalty_tier="silver",
        customer_acquisition_channel="organic_search",
        preferred_contact_method="sms",
        marketing_opt_in=True,
    )
