"""Streamlit portfolio demonstration UI for DealerAI Ops."""

from __future__ import annotations

import importlib
from typing import Any

import pandas as pd

from dealerai_ops.agents.schemas import AgentRunResult, AgentStatus, ConversationState
from dealerai_ops.ui.demo_agent import run_demo_agent_turn, sample_prompts, trace_frame_rows
from dealerai_ops.ui.demo_data import (
    appointment_status_mix,
    appointments_frame,
    architecture_layers,
    build_demo_session_factory,
    build_demo_snapshot,
    customer_detail,
    customers_frame,
    escalations_frame,
    evaluation_metrics_frame,
    gate_metrics_frame,
    gate_status,
    inventory_frame,
    inventory_mix,
    load_rag_documents,
    no_show_risk_frame,
    overview_metrics,
    owned_vehicles_frame,
    retrieve_demo_sources,
    risk_tier_mix,
    service_slots_frame,
    threshold_config_summary,
)


def main() -> None:
    """Run the Streamlit UI."""
    st = _load_streamlit()
    st.set_page_config(
        page_title="DealerAI Ops Demo",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _apply_style(st)

    snapshot = st.cache_resource(build_demo_snapshot)()
    session_factory = st.cache_resource(build_demo_session_factory)()

    st.title("DealerAI Ops")
    st.caption(
        "Production-grade agentic AI and predictive intelligence for synthetic dealership "
        "operations."
    )
    _render_header_metrics(st, snapshot)

    tabs = st.tabs(
        [
            "AI Service Assistant",
            "Customer 360",
            "Vehicle Inventory",
            "Service Appointments",
            "No-Show Risk",
            "Agent Trace",
            "RAG Sources",
            "Evaluation Dashboard",
            "Human Escalations",
            "System Architecture",
        ]
    )

    with tabs[0]:
        _render_assistant(st, snapshot, session_factory)
    with tabs[1]:
        _render_customer_360(st, snapshot)
    with tabs[2]:
        _render_inventory(st, snapshot)
    with tabs[3]:
        _render_appointments(st, snapshot)
    with tabs[4]:
        _render_no_show_risk(st, snapshot)
    with tabs[5]:
        _render_agent_trace(st)
    with tabs[6]:
        _render_rag_sources(st)
    with tabs[7]:
        _render_evaluation_dashboard(st)
    with tabs[8]:
        _render_escalations(st, snapshot)
    with tabs[9]:
        _render_architecture(st)


def _load_streamlit() -> Any:
    try:
        return importlib.import_module("streamlit")
    except ModuleNotFoundError as exc:
        if exc.name == "streamlit":
            raise RuntimeError(
                "Streamlit is not installed. Run `python -m pip install -e .` and then "
                "`make demo-ui`."
            ) from exc
        raise


def _apply_style(st: Any) -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
        [data-testid="stMetric"] {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 0.65rem 0.8rem;
            background: #ffffff;
        }
        div[data-testid="stDataFrame"] { border: 1px solid #e5e7eb; border-radius: 8px; }
        .small-note { color: #64748b; font-size: 0.9rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header_metrics(st: Any, snapshot: Any) -> None:
    metrics = overview_metrics(snapshot)
    columns = st.columns(6)
    columns[0].metric("Customers", f"{metrics['customers']:,}")
    columns[1].metric("Owned Vehicles", f"{metrics['owned_vehicles']:,}")
    columns[2].metric("Inventory", f"{metrics['inventory']:,}")
    columns[3].metric("Appointments", f"{metrics['appointments']:,}")
    columns[4].metric("Future Slots", f"{metrics['future_slots']:,}")
    columns[5].metric("Escalations", f"{metrics['escalations']:,}")


def _render_assistant(st: Any, snapshot: Any, session_factory: Any) -> None:
    st.subheader("AI Service Assistant")
    st.caption(
        "Deterministic local agent mode. Tool execution, retrieval, confirmation, and final "
        "answers are visible; hidden reasoning is not displayed."
    )

    prompts = sample_prompts(snapshot)
    selected = st.selectbox("Scenario", list(prompts), index=0)
    user_message = st.text_area("Customer request", value=prompts[selected], height=90)
    confirmed = st.checkbox("Explicitly confirm pending write action")

    left, right = st.columns([1, 1])
    run_clicked = left.button("Run assistant turn", type="primary", use_container_width=True)
    clear_clicked = right.button("Reset conversation", use_container_width=True)

    if clear_clicked:
        st.session_state["demo_agent_state"] = None
        st.session_state["demo_agent_result"] = None
        st.session_state["demo_agent_spans"] = []

    if run_clicked:
        prior_state = st.session_state.get("demo_agent_state")
        turn = run_demo_agent_turn(
            snapshot=snapshot,
            session_factory=session_factory,
            user_message=user_message,
            confirmed=confirmed,
            state=prior_state if isinstance(prior_state, ConversationState) else None,
        )
        st.session_state["demo_agent_state"] = turn.result.state
        st.session_state["demo_agent_result"] = turn.result
        st.session_state["demo_agent_spans"] = trace_frame_rows(turn.spans)

    result = st.session_state.get("demo_agent_result")
    if not isinstance(result, AgentRunResult):
        st.info("Run a scenario to inspect the operational path.")
        return

    _render_conversation(st, result)
    _render_sources(st, result)
    _render_tool_activity(st, result)
    _render_confirmation(st, result)
    _render_final_outcome(st, result)


def _render_conversation(st: Any, result: AgentRunResult) -> None:
    st.markdown("#### Conversation")
    for message in result.state.messages:
        if message.role.value == "tool":
            st.code(_summarize_tool_message(message.content), language="json")
        else:
            with st.chat_message(message.role.value):
                st.write(message.content)


def _render_sources(st: Any, result: AgentRunResult) -> None:
    st.markdown("#### Retrieved Sources")
    if not result.citations:
        st.caption("No retrieval was needed for this turn.")
        return
    st.dataframe(
        pd.DataFrame([citation.model_dump() for citation in result.citations]),
        hide_index=True,
        use_container_width=True,
    )


def _render_tool_activity(st: Any, result: AgentRunResult) -> None:
    st.markdown("#### Tool Activity")
    if not result.state.tool_results:
        st.caption("No typed tools were requested.")
        return
    rows = []
    for tool_result in result.state.tool_results:
        rows.append(
            {
                "request_id": tool_result.request_id,
                "tool": tool_result.tool_name,
                "outcome": tool_result.outcome.value,
                "idempotent_replay": tool_result.idempotent_replay,
                "error": tool_result.error.code if tool_result.error else "",
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _render_confirmation(st: Any, result: AgentRunResult) -> None:
    st.markdown("#### Confirmation Requests")
    if (
        result.status != AgentStatus.REQUIRES_CONFIRMATION
        or result.state.pending_confirmation is None
    ):
        st.caption("No pending confirmation.")
        return
    pending = result.state.pending_confirmation
    st.warning(f"`{pending.tool_name}` requires explicit user confirmation before execution.")
    st.json(pending.arguments)


def _render_final_outcome(st: Any, result: AgentRunResult) -> None:
    st.markdown("#### Final Outcome")
    status = result.status.value
    if result.status == AgentStatus.COMPLETED:
        st.success(result.final_answer or "Completed.")
    elif result.status == AgentStatus.REQUIRES_CONFIRMATION:
        st.warning(result.final_answer or "Confirmation required.")
    elif result.status == AgentStatus.ESCALATED:
        st.info(result.final_answer or "Escalated to a human team.")
    else:
        st.error(result.error.message if result.error else "Agent run failed.")
    st.caption(f"Status: `{status}`")


def _render_customer_360(st: Any, snapshot: Any) -> None:
    st.subheader("Customer 360")
    customers = customers_frame(snapshot, limit=50)
    selected_customer = st.selectbox("Synthetic customer", customers["customer_id"].tolist())
    detail = customer_detail(snapshot, selected_customer)
    columns = st.columns(4)
    columns[0].metric("Loyalty", detail["loyalty_tier"])
    columns[1].metric("Vehicles", detail["vehicles"])
    columns[2].metric("Appointments", detail["appointments"])
    columns[3].metric("Prior No-Shows", detail["prior_no_shows"])
    st.dataframe(customers, hide_index=True, use_container_width=True)
    st.markdown("#### Owned Vehicles")
    st.dataframe(
        owned_vehicles_frame(snapshot, selected_customer),
        hide_index=True,
        use_container_width=True,
    )


def _render_inventory(st: Any, snapshot: Any) -> None:
    st.subheader("Vehicle Inventory")
    frame = inventory_frame(snapshot, limit=80)
    statuses = sorted(frame["status"].unique())
    status_filter = st.multiselect("Status", statuses, default=statuses)
    filtered = frame[frame["status"].isin(status_filter)] if status_filter else frame
    st.bar_chart(inventory_mix(snapshot), x="status", y="count")
    st.dataframe(filtered, hide_index=True, use_container_width=True)


def _render_appointments(st: Any, snapshot: Any) -> None:
    st.subheader("Service Appointments")
    st.bar_chart(appointment_status_mix(snapshot), x="status", y="count")
    appointments = appointments_frame(snapshot, limit=100)
    slots = service_slots_frame(snapshot, limit=50)
    left, right = st.columns([2, 1])
    left.dataframe(appointments, hide_index=True, use_container_width=True)
    right.dataframe(slots, hide_index=True, use_container_width=True)


def _render_no_show_risk(st: Any, snapshot: Any) -> None:
    st.subheader("No-Show Risk")
    risk_frame = no_show_risk_frame(snapshot, limit=90)
    st.bar_chart(risk_tier_mix(snapshot), x="risk_tier", y="count")
    st.dataframe(
        risk_frame.sort_values("probability", ascending=False),
        hide_index=True,
        use_container_width=True,
    )


def _render_agent_trace(st: Any) -> None:
    st.subheader("Agent Trace")
    st.caption(
        "Operational trace only: model calls, retrieval, tools, guardrails, escalation, and "
        "latency."
    )
    rows = st.session_state.get("demo_agent_spans", [])
    if not rows:
        st.info("Run an assistant scenario first to populate the trace.")
        return
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _render_rag_sources(st: Any) -> None:
    st.subheader("RAG Sources")
    query = st.text_input(
        "Retrieval query",
        value="What is the fictional service scheduling policy?",
    )
    source_rows = retrieve_demo_sources(query, top_k=5)
    st.dataframe(source_rows, hide_index=True, use_container_width=True)
    docs = load_rag_documents()
    st.markdown("#### Synthetic Corpus")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "document_id": document.document_id,
                    "title": document.title,
                    "synthetic": document.synthetic,
                    "source_path": document.source_path,
                }
                for document in docs
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )


def _render_evaluation_dashboard(st: Any) -> None:
    st.subheader("Evaluation Dashboard")
    gate = gate_status()
    metrics = evaluation_metrics_frame()
    gate_metrics = gate_metrics_frame()
    columns = st.columns(4)
    columns[0].metric("Task Success", _metric_value(metrics, "task_success"))
    columns[1].metric("Tool Accuracy", _metric_value(gate_metrics, "tool_selection_accuracy"))
    columns[2].metric("RAG Hit Rate", _metric_value(gate_metrics, "rag_retrieval_hit_rate"))
    columns[3].metric("Gate", "Accepted" if gate["accepted"] else "Failed")

    scorer_metrics = metrics[
        metrics["metric"].isin(
            [
                "task_success",
                "expected_tool_called",
                "retrieval_hit",
                "PII_leakage",
                "required_escalation",
                "hallucinated_transaction",
            ]
        )
    ]
    st.bar_chart(scorer_metrics, x="metric", y="value")
    st.markdown("#### Regression Gate")
    st.dataframe(gate_metrics, hide_index=True, use_container_width=True)
    with st.expander("Version-controlled thresholds"):
        st.json(threshold_config_summary())


def _render_escalations(st: Any, snapshot: Any) -> None:
    st.subheader("Human Escalations")
    frame = escalations_frame(snapshot, limit=50)
    st.dataframe(frame, hide_index=True, use_container_width=True)


def _render_architecture(st: Any) -> None:
    st.subheader("System Architecture")
    st.dataframe(architecture_layers(), hide_index=True, use_container_width=True)
    st.markdown(
        """
        ```mermaid
        flowchart LR
          UI["Streamlit Demo UI"] --> API["FastAPI"]
          API --> Agent["Agent Orchestrator"]
          Agent --> Guardrails["Guardrails"]
          Agent --> RAG["RAG Retriever"]
          Agent --> Tools["Typed Tools"]
          Tools --> Domain["Domain Services"]
          Domain --> DB["SQLAlchemy: SQLite local / PostgreSQL ready"]
          Tools --> ML["No-Show ML Service"]
          Agent --> Escalation["Human Escalation"]
          Agent --> Observability["Redacted Trace Spans"]
          Evaluation["Evaluation Lab + Release Gate"] --> Agent
        ```
        """
    )


def _metric_value(frame: pd.DataFrame, name: str) -> str:
    match = frame[frame["metric" if "metric" in frame.columns else "name"] == name]
    if match.empty:
        return "n/a"
    value = float(match.iloc[0]["value"])
    return f"{value:.0%}" if value <= 1 else f"{value:.2f}"


def _summarize_tool_message(content: str) -> str:
    if len(content) <= 800:
        return content
    return f"{content[:800]}..."


if __name__ == "__main__":
    main()
