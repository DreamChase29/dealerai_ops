"""Lightweight tracing with optional MLflow integration."""

from __future__ import annotations

import contextlib
import contextvars
import importlib
from collections.abc import Generator, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from time import perf_counter
from typing import Any, Protocol

import structlog
from pydantic import BaseModel, ConfigDict, Field

from dealerai_ops.core.config import Settings
from dealerai_ops.core.redaction import redact_value

logger = structlog.get_logger(__name__)

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "dealerai_correlation_id",
    default=None,
)
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "dealerai_request_id",
    default=None,
)
_conversation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "dealerai_conversation_id",
    default=None,
)


class SpanStatus(StrEnum):
    """Terminal status for a trace span."""

    OK = "ok"
    ERROR = "error"


class SpanRecord(BaseModel):
    """Redacted trace span emitted to configured telemetry sinks."""

    model_config = ConfigDict(extra="forbid")

    name: str
    correlation_id: str | None = None
    request_id: str | None = None
    conversation_id: str | None = None
    started_at: str
    latency_ms: float
    status: SpanStatus
    attributes: dict[str, Any] = Field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None


class TelemetrySink(Protocol):
    """Destination for redacted span records."""

    def record_span(self, span: SpanRecord) -> None:
        """Record one completed span."""


class StructuredLogTelemetrySink:
    """Emit spans to structured logs."""

    def record_span(self, span: SpanRecord) -> None:
        """Log a completed span."""
        logger.info("observability_span", **span.model_dump(mode="json"))


class InMemoryTelemetrySink:
    """Test sink that stores spans in process memory."""

    def __init__(self) -> None:
        self.spans: list[SpanRecord] = []

    def record_span(self, span: SpanRecord) -> None:
        """Store one completed span."""
        self.spans.append(span)


class CompositeTelemetrySink:
    """Fan out spans to multiple sinks."""

    def __init__(self, sinks: list[TelemetrySink]) -> None:
        self.sinks = sinks

    def record_span(self, span: SpanRecord) -> None:
        """Record one completed span to all sinks."""
        for sink in self.sinks:
            sink.record_span(span)


class MLflowTelemetrySink:
    """Optional MLflow sink using local or remote tracking URI."""

    def __init__(self, tracking_uri: str, experiment_name: str) -> None:
        self._mlflow: Any = importlib.import_module("mlflow")
        self._mlflow.set_tracking_uri(tracking_uri)
        self._mlflow.set_experiment(experiment_name)

    def record_span(self, span: SpanRecord) -> None:
        """Log a span as an MLflow run with metrics and redacted tags."""
        tags = {
            "span.name": span.name,
            "span.status": span.status.value,
            "correlation_id": span.correlation_id or "",
            "request_id": span.request_id or "",
            "conversation_id": span.conversation_id or "",
        }
        for key, value in span.attributes.items():
            if isinstance(value, str | int | float | bool):
                tags[f"attr.{key}"] = str(value)
        with self._mlflow.start_run(run_name=span.name, nested=True):
            self._mlflow.set_tags(tags)
            self._mlflow.log_metric("latency_ms", span.latency_ms)
            if span.error_type is not None:
                self._mlflow.set_tag("error.type", span.error_type)
            if span.error_message is not None:
                self._mlflow.set_tag("error.message", span.error_message)


class Span:
    """Mutable span context used by instrumentation sites."""

    def __init__(
        self,
        name: str,
        attributes: Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
        request_id: str | None = None,
        conversation_id: str | None = None,
    ) -> None:
        self.name = name
        self.attributes: dict[str, Any] = dict(attributes or {})
        self.correlation_id = correlation_id or _correlation_id.get()
        self.request_id = request_id or _request_id.get()
        self.conversation_id = conversation_id or _conversation_id.get()
        self.started_at = datetime.now(UTC)
        self._started_counter = perf_counter()
        self.status = SpanStatus.OK
        self.error_type: str | None = None
        self.error_message: str | None = None

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a redacted span attribute before emission."""
        self.attributes[key] = value

    def set_attributes(self, values: Mapping[str, Any]) -> None:
        """Set multiple span attributes before emission."""
        self.attributes.update(values)

    def mark_error(self, message: str, error_type: str | None = None) -> None:
        """Mark the span as failed without raising an exception."""
        self.status = SpanStatus.ERROR
        self.error_message = message
        self.error_type = error_type

    def to_record(self) -> SpanRecord:
        """Return a redacted completed span record."""
        latency_ms = (perf_counter() - self._started_counter) * 1000
        return SpanRecord(
            name=self.name,
            correlation_id=self.correlation_id,
            request_id=self.request_id,
            conversation_id=self.conversation_id,
            started_at=self.started_at.isoformat(),
            latency_ms=latency_ms,
            status=self.status,
            attributes=redact_value(self.attributes),
            error_type=self.error_type,
            error_message=redact_value(self.error_message),
        )


class _NoopTelemetrySink:
    def record_span(self, span: SpanRecord) -> None:
        del span


_telemetry_sink: TelemetrySink = _NoopTelemetrySink()


def set_telemetry_sink(sink: TelemetrySink) -> None:
    """Override the process-level telemetry sink, primarily for tests."""
    global _telemetry_sink
    _telemetry_sink = sink


def configure_observability(settings: Settings) -> None:
    """Configure structured-log and optional MLflow telemetry sinks."""
    sinks: list[TelemetrySink] = []
    if settings.observability_enabled:
        sinks.append(StructuredLogTelemetrySink())
    if settings.mlflow_enabled:
        mlflow_sink = _build_mlflow_sink(settings)
        if mlflow_sink is not None:
            sinks.append(mlflow_sink)
    set_telemetry_sink(CompositeTelemetrySink(sinks) if sinks else _NoopTelemetrySink())


@contextlib.contextmanager
def start_span(
    name: str,
    attributes: Mapping[str, Any] | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
    conversation_id: str | None = None,
) -> Generator[Span, None, None]:
    """Start and emit a trace span."""
    span = Span(
        name=name,
        attributes=attributes,
        correlation_id=correlation_id,
        request_id=request_id,
        conversation_id=conversation_id,
    )
    correlation_token = _correlation_id.set(span.correlation_id)
    request_token = _request_id.set(span.request_id)
    conversation_token = _conversation_id.set(span.conversation_id)
    try:
        yield span
    except Exception as exc:
        span.mark_error(str(exc), type(exc).__name__)
        raise
    finally:
        _telemetry_sink.record_span(span.to_record())
        _conversation_id.reset(conversation_token)
        _request_id.reset(request_token)
        _correlation_id.reset(correlation_token)


def _build_mlflow_sink(settings: Settings) -> MLflowTelemetrySink | None:
    try:
        return MLflowTelemetrySink(
            tracking_uri=settings.mlflow_tracking_uri,
            experiment_name=settings.mlflow_experiment_name,
        )
    except ModuleNotFoundError as exc:
        if exc.name != "mlflow":
            raise
        logger.warning(
            "mlflow_observability_disabled",
            reason="mlflow_package_not_installed",
            tracking_uri=settings.mlflow_tracking_uri,
        )
        return None
