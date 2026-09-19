"""Tests for the portfolio demo UI support layer."""

from dealerai_ops.agents.schemas import AgentStatus
from dealerai_ops.ui.demo_agent import run_demo_agent_turn, sample_prompts, trace_frame_rows
from dealerai_ops.ui.demo_data import (
    appointment_status_mix,
    architecture_layers,
    build_demo_session_factory,
    build_demo_snapshot,
    customers_frame,
    evaluation_metrics_frame,
    gate_metrics_frame,
    gate_status,
    inventory_frame,
    no_show_risk_frame,
    retrieve_demo_sources,
)


def test_demo_snapshot_is_deterministic() -> None:
    first = build_demo_snapshot()
    second = build_demo_snapshot()

    assert first.customer_id == second.customer_id
    assert first.vehicle_id == second.vehicle_id
    assert len(first.dataset.customers) == 240
    assert len(first.dataset.inventory_vehicles) == 80


def test_demo_frames_have_expected_columns() -> None:
    snapshot = build_demo_snapshot()

    assert {"customer_id", "name", "prior_no_shows"}.issubset(customers_frame(snapshot).columns)
    assert {"stock", "make", "price", "status"}.issubset(inventory_frame(snapshot).columns)
    assert {"status", "count"}.issubset(appointment_status_mix(snapshot).columns)
    assert {"appointment_id", "probability", "risk_tier"}.issubset(
        no_show_risk_frame(snapshot).columns
    )


def test_demo_retrieval_returns_citation_ready_rows() -> None:
    rows = retrieve_demo_sources("fictional service scheduling policy", top_k=3)

    assert len(rows) == 3
    assert {"document_id", "title", "section", "chunk_id", "score"}.issubset(rows.columns)


def test_evaluation_dashboard_inputs_load_committed_reports() -> None:
    metrics = evaluation_metrics_frame()
    gate_metrics = gate_metrics_frame()
    status = gate_status()

    assert "task_success" in set(metrics["metric"])
    assert "tool_selection_accuracy" in set(gate_metrics["name"])
    assert status["accepted"] is True


def test_architecture_layers_include_ui_and_quality() -> None:
    layers = set(architecture_layers()["layer"])

    assert {"UI", "Agent", "Quality"}.issubset(layers)


def test_demo_agent_booking_requires_confirmation_then_succeeds() -> None:
    snapshot = build_demo_snapshot()
    session_factory = build_demo_session_factory()
    prompt = sample_prompts(snapshot)["Book appointment"]

    first_turn = run_demo_agent_turn(snapshot, session_factory, prompt)
    assert first_turn.result.status == AgentStatus.REQUIRES_CONFIRMATION
    assert first_turn.result.state.pending_confirmation is not None

    second_turn = run_demo_agent_turn(
        snapshot,
        session_factory,
        prompt,
        confirmed=True,
        state=first_turn.result.state,
    )

    assert second_turn.result.status == AgentStatus.COMPLETED
    assert any(
        result.tool_name == "book_service_appointment" and result.outcome.value == "succeeded"
        for result in second_turn.result.state.tool_results
    )
    assert trace_frame_rows(second_turn.spans)
