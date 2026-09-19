"""Synthetic data helpers for the Streamlit portfolio demo."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session, sessionmaker

from dealerai_ops.db.base import Base
from dealerai_ops.db.session import create_db_engine, create_session_factory
from dealerai_ops.domain.enums import AppointmentStatus
from dealerai_ops.domain.synthetic import (
    DEFAULT_SYNTHETIC_SEED,
    SyntheticDataset,
    SyntheticDatasetCounts,
    generate_synthetic_dataset,
    seed_session,
)
from dealerai_ops.evals.gate import load_threshold_config
from dealerai_ops.evals.schemas import EvaluationRunReport
from dealerai_ops.ml.risk import risk_tier_for_probability
from dealerai_ops.rag.loader import load_knowledge_documents
from dealerai_ops.rag.retriever import build_local_retriever
from dealerai_ops.rag.schemas import KnowledgeDocument

DEMO_AS_OF = datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
DEMO_COUNTS = SyntheticDatasetCounts(
    customers=240,
    owned_vehicles=300,
    inventory_vehicles=80,
    historical_appointments=650,
    future_service_days=21,
    sales_leads=90,
    conversations=80,
    tool_executions=120,
    escalations=16,
)


@dataclass(frozen=True)
class DemoSnapshot:
    """In-memory synthetic dataset plus IDs used by the demo assistant."""

    dataset: SyntheticDataset
    customer_id: str
    vehicle_id: str
    appointment_id: str
    slot_id: str
    conversation_id: str


def build_demo_snapshot() -> DemoSnapshot:
    """Build the deterministic synthetic dataset used by the Streamlit UI."""
    dataset = generate_synthetic_dataset(
        counts=DEMO_COUNTS,
        seed=DEFAULT_SYNTHETIC_SEED,
        as_of=DEMO_AS_OF,
    )
    vehicle = dataset.vehicles[0]
    appointment = dataset.service_appointments[0]
    slot = next(slot for slot in dataset.service_slots if slot.booked_count < slot.capacity)
    conversation = dataset.conversations[0]
    return DemoSnapshot(
        dataset=dataset,
        customer_id=vehicle.customer_id,
        vehicle_id=vehicle.id,
        appointment_id=appointment.id,
        slot_id=slot.id,
        conversation_id=conversation.id,
    )


def build_demo_session_factory() -> sessionmaker[Session]:
    """Return a seeded in-memory SQLite session factory for demo tool execution."""
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        seed_session(session, build_demo_snapshot().dataset)
    return session_factory


def overview_metrics(snapshot: DemoSnapshot) -> dict[str, int]:
    """Return high-level dataset metrics for the demo header."""
    dataset = snapshot.dataset
    return {
        "customers": len(dataset.customers),
        "owned_vehicles": len(dataset.vehicles),
        "inventory": len(dataset.inventory_vehicles),
        "appointments": len(dataset.service_appointments),
        "future_slots": len(dataset.service_slots),
        "escalations": len(dataset.escalations),
    }


def customers_frame(snapshot: DemoSnapshot, limit: int = 30) -> pd.DataFrame:
    """Return redacted customer 360 rows."""
    rows = [
        {
            "customer_id": customer.id,
            "name": customer.synthetic_name,
            "contact": customer.preferred_contact_method,
            "loyalty": customer.loyalty_tier,
            "distance_miles": float(customer.distance_miles),
            "completed": customer.total_completed_appointments,
            "prior_no_shows": customer.prior_no_show_count,
            "marketing_opt_in": customer.marketing_opt_in,
        }
        for customer in snapshot.dataset.customers[:limit]
    ]
    return pd.DataFrame(rows)


def customer_detail(snapshot: DemoSnapshot, customer_id: str) -> dict[str, Any]:
    """Return a synthetic customer profile for display."""
    customer = next(
        customer for customer in snapshot.dataset.customers if customer.id == customer_id
    )
    vehicles = [
        vehicle for vehicle in snapshot.dataset.vehicles if vehicle.customer_id == customer_id
    ]
    appointments = [
        appointment
        for appointment in snapshot.dataset.service_appointments
        if appointment.customer_id == customer_id
    ]
    return {
        "customer_id": customer.id,
        "name": customer.synthetic_name,
        "preferred_contact": customer.preferred_contact_method,
        "loyalty_tier": customer.loyalty_tier,
        "distance_miles": float(customer.distance_miles),
        "vehicles": len(vehicles),
        "appointments": len(appointments),
        "prior_no_shows": customer.prior_no_show_count,
    }


def owned_vehicles_frame(snapshot: DemoSnapshot, customer_id: str) -> pd.DataFrame:
    """Return owned vehicles for one customer."""
    rows = [
        {
            "vehicle_id": vehicle.id,
            "year": vehicle.model_year,
            "make": vehicle.make,
            "model": vehicle.model,
            "trim": vehicle.trim,
            "mileage": vehicle.current_mileage,
            "warranty_end": vehicle.warranty_end_date.date().isoformat(),
        }
        for vehicle in snapshot.dataset.vehicles
        if vehicle.customer_id == customer_id
    ]
    return pd.DataFrame(rows)


def inventory_frame(snapshot: DemoSnapshot, limit: int = 50) -> pd.DataFrame:
    """Return inventory rows for display."""
    rows = [
        {
            "stock": vehicle.stock_number,
            "year": vehicle.model_year,
            "make": vehicle.make,
            "model": vehicle.model,
            "trim": vehicle.trim,
            "body": vehicle.body_style,
            "fuel": vehicle.fuel_type,
            "price": float(vehicle.list_price),
            "status": vehicle.status.value,
        }
        for vehicle in snapshot.dataset.inventory_vehicles[:limit]
    ]
    return pd.DataFrame(rows)


def appointments_frame(snapshot: DemoSnapshot, limit: int = 80) -> pd.DataFrame:
    """Return service appointment rows."""
    rows = [
        {
            "appointment_id": appointment.id,
            "customer_id": appointment.customer_id,
            "vehicle_id": appointment.vehicle_id,
            "status": appointment.status.value,
            "type": appointment.appointment_type.value,
            "channel": appointment.channel.value,
            "scheduled": appointment.scheduled_start_at.isoformat(),
            "lead_time_days": appointment.lead_time_days,
            "prior_no_shows": appointment.prior_no_show_count_at_booking,
        }
        for appointment in snapshot.dataset.service_appointments[:limit]
    ]
    return pd.DataFrame(rows)


def service_slots_frame(snapshot: DemoSnapshot, limit: int = 40) -> pd.DataFrame:
    """Return future service-slot capacity rows."""
    rows = [
        {
            "slot_id": slot.id,
            "starts": slot.starts_at.isoformat(),
            "bay": slot.bay_type,
            "advisor": slot.advisor_id,
            "capacity": slot.capacity,
            "booked": slot.booked_count,
            "remaining": slot.capacity - slot.booked_count,
        }
        for slot in snapshot.dataset.service_slots[:limit]
    ]
    return pd.DataFrame(rows)


def no_show_risk_frame(snapshot: DemoSnapshot, limit: int = 60) -> pd.DataFrame:
    """Return deterministic operational risk estimates for service appointments."""
    customer_by_id = {customer.id: customer for customer in snapshot.dataset.customers}
    rows = []
    for appointment in snapshot.dataset.service_appointments[:limit]:
        customer = customer_by_id[appointment.customer_id]
        probability = _demo_no_show_probability(
            prior_no_shows=appointment.prior_no_show_count_at_booking,
            lead_time_days=appointment.lead_time_days,
            reminder_count=appointment.reminder_count,
            distance_miles=customer.distance_miles,
            status=appointment.status,
        )
        rows.append(
            {
                "appointment_id": appointment.id,
                "customer_id": appointment.customer_id,
                "type": appointment.appointment_type.value,
                "channel": appointment.channel.value,
                "probability": probability,
                "risk_tier": risk_tier_for_probability(probability).value,
                "status": appointment.status.value,
            }
        )
    return pd.DataFrame(rows)


def escalations_frame(snapshot: DemoSnapshot, limit: int = 40) -> pd.DataFrame:
    """Return synthetic human escalation rows."""
    rows = [
        {
            "escalation_id": escalation.id,
            "conversation_id": escalation.conversation_id,
            "customer_id": escalation.customer_id,
            "reason": escalation.reason_code,
            "severity": escalation.severity,
            "status": escalation.status.value,
            "team": escalation.assigned_team,
            "created": escalation.created_at.isoformat(),
        }
        for escalation in snapshot.dataset.escalations[:limit]
    ]
    return pd.DataFrame(rows)


def inventory_mix(snapshot: DemoSnapshot) -> pd.DataFrame:
    """Return inventory status counts."""
    frame = inventory_frame(snapshot, limit=len(snapshot.dataset.inventory_vehicles))
    return frame.groupby("status", as_index=False).size().rename(columns={"size": "count"})


def appointment_status_mix(snapshot: DemoSnapshot) -> pd.DataFrame:
    """Return appointment status counts."""
    frame = appointments_frame(snapshot, limit=len(snapshot.dataset.service_appointments))
    return frame.groupby("status", as_index=False).size().rename(columns={"size": "count"})


def risk_tier_mix(snapshot: DemoSnapshot) -> pd.DataFrame:
    """Return no-show risk tier counts."""
    frame = no_show_risk_frame(snapshot, limit=120)
    return frame.groupby("risk_tier", as_index=False).size().rename(columns={"size": "count"})


def load_rag_documents(knowledge_dir: str | Path = "knowledge") -> list[KnowledgeDocument]:
    """Load synthetic knowledge documents for the RAG Sources page."""
    return load_knowledge_documents(knowledge_dir)


def retrieve_demo_sources(query: str, top_k: int = 5) -> pd.DataFrame:
    """Retrieve citation-ready chunks for a query."""
    retriever = build_local_retriever("knowledge")
    rows = [
        {
            "document_id": chunk.document_id,
            "title": chunk.title,
            "section": chunk.section,
            "chunk_id": chunk.chunk_id,
            "score": round(chunk.score, 4),
        }
        for chunk in retriever.retrieve(query, top_k=top_k)
    ]
    return pd.DataFrame(rows)


def evaluation_metrics_frame(
    results_path: str | Path = "evaluation/results/latest.json",
) -> pd.DataFrame:
    """Return evaluation scorer pass rates for dashboard charts."""
    report = EvaluationRunReport.model_validate_json(Path(results_path).read_text(encoding="utf-8"))
    rows = [
        {"metric": scorer, "value": rate}
        for scorer, rate in report.aggregate_metrics.scorer_pass_rate.items()
    ]
    return pd.DataFrame(rows)


def gate_metrics_frame(
    gate_path: str | Path = "evaluation/results/quality_gate.json",
) -> pd.DataFrame:
    """Return release gate metrics for dashboard display."""
    data = json.loads(Path(gate_path).read_text(encoding="utf-8"))
    metrics = data["metrics"] if isinstance(data, dict) else []
    return pd.DataFrame(metrics)


def gate_status(gate_path: str | Path = "evaluation/results/quality_gate.json") -> dict[str, Any]:
    """Return release gate status metadata."""
    data = json.loads(Path(gate_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"accepted": False, "threshold_version": "unknown"}
    return {
        "accepted": bool(data.get("accepted", False)),
        "threshold_version": str(data.get("threshold_version", "unknown")),
    }


def threshold_config_summary(
    path: str | Path = "evaluation/quality_thresholds.json",
) -> dict[str, Any]:
    """Return the committed release gate threshold configuration."""
    config = load_threshold_config(Path(path))
    return config.model_dump(mode="json")


def architecture_layers() -> pd.DataFrame:
    """Return architecture layers for display."""
    return pd.DataFrame(
        [
            {"layer": "UI", "components": "Streamlit portfolio demo"},
            {"layer": "API", "components": "FastAPI health, agent, ML, escalation routes"},
            {"layer": "Agent", "components": "Provider interface, orchestration, guardrails"},
            {"layer": "Tools", "components": "Typed Pydantic tools, audit, idempotency"},
            {"layer": "RAG", "components": "Synthetic corpus, chunking, local vector retrieval"},
            {"layer": "ML", "components": "sklearn no-show model and risk bands"},
            {"layer": "Data", "components": "SQLAlchemy domain model, PostgreSQL-ready"},
            {"layer": "Quality", "components": "Evaluation lab, regression gate, observability"},
        ]
    )


def _demo_no_show_probability(
    prior_no_shows: int,
    lead_time_days: int,
    reminder_count: int,
    distance_miles: Decimal,
    status: AppointmentStatus,
) -> float:
    probability = 0.06
    probability += min(prior_no_shows, 4) * 0.035
    probability += max(0, lead_time_days - 14) * 0.003
    probability -= min(reminder_count, 3) * 0.015
    probability += 0.025 if distance_miles > Decimal("30.00") else 0
    probability += 0.08 if status == AppointmentStatus.NO_SHOW else 0
    return round(min(max(probability, 0.01), 0.72), 4)
