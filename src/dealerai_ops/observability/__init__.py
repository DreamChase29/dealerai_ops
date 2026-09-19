"""Observability primitives for DealerAI Ops."""

from dealerai_ops.observability.tracing import (
    InMemoryTelemetrySink,
    configure_observability,
    set_telemetry_sink,
    start_span,
)

__all__ = [
    "InMemoryTelemetrySink",
    "configure_observability",
    "set_telemetry_sink",
    "start_span",
]
