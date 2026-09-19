from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs" / "dealerai_ops_interview_review.pdf"


ACCENT = colors.HexColor("#245C5A")
INK = colors.HexColor("#1E2428")
MUTED = colors.HexColor("#5E6A70")
LINE = colors.HexColor("#D8DEE2")
SOFT = colors.HexColor("#F5F7F8")
WARN = colors.HexColor("#8A4B2B")


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=29,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=10,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=15,
            textColor=MUTED,
            spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "Heading1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=ACCENT,
            spaceBefore=16,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "Heading2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=15,
            textColor=INK,
            spaceBefore=8,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.4,
            leading=13.2,
            textColor=INK,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=11.3,
            textColor=MUTED,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.9,
            leading=12.5,
            textColor=INK,
            leftIndent=10,
            firstLineIndent=0,
            spaceAfter=3,
        ),
        "table": ParagraphStyle(
            "Table",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.4,
            leading=9.6,
            textColor=INK,
        ),
        "table_head": ParagraphStyle(
            "TableHead",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.6,
            leading=9.8,
            textColor=colors.white,
        ),
        "callout": ParagraphStyle(
            "Callout",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.8,
            leading=12.5,
            textColor=INK,
            backColor=SOFT,
            borderColor=LINE,
            borderWidth=0.5,
            borderPadding=8,
            spaceAfter=10,
        ),
        "mono": ParagraphStyle(
            "Mono",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.2,
            leading=9.2,
            textColor=INK,
            backColor=SOFT,
            borderColor=LINE,
            borderWidth=0.4,
            borderPadding=7,
            spaceAfter=8,
        ),
    }


S = styles()


def p(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, S[style])


def bullets(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(p(item, "bullet"), bulletColor=ACCENT) for item in items],
        bulletType="bullet",
        start="circle",
        leftIndent=14,
    )


def numbered(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(p(item, "bullet")) for item in items],
        bulletType="1",
        leftIndent=18,
    )


def table(rows: list[list[str]], widths: list[float]) -> Table:
    data = [[p(cell, "table_head" if idx == 0 else "table") for cell in row] for idx, row in enumerate(rows)]
    tbl = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT]),
            ]
        )
    )
    return tbl


def on_page(canvas, doc):
    canvas.saveState()
    width, height = LETTER
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(0.65 * inch, height - 0.55 * inch, width - 0.65 * inch, height - 0.55 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.65 * inch, 0.38 * inch, "DealerAI Ops - Senior Data Scientist Interview Review")
    canvas.drawRightString(width - 0.65 * inch, 0.38 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=LETTER,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.65 * inch,
        title="DealerAI Ops Interview Review",
        author="Codex",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="default", frames=[frame], onPage=on_page)])

    story = []
    story.append(p("DealerAI Ops", "title"))
    story.append(
        p(
            "Senior Data Scientist / AI Engineer Interview Review<br/>"
            "Agentic AI, Tool Calling, RAG, Predictive ML, AWS-Ready Architecture, MLOps",
            "subtitle",
        )
    )
    story.append(
        p(
            "Scope: This document analyzes only capabilities implemented in the repository. "
            "It intentionally distinguishes local/reference implementation from proposed AWS production mappings.",
            "callout",
        )
    )

    story.append(p("1. 90-Second Explanation", "h1"))
    story.append(
        p(
            "DealerAI Ops is a production-oriented portfolio implementation of an agentic AI and predictive "
            "intelligence platform for a synthetic automotive dealership. It combines a FastAPI backend, typed "
            "service/repository layers, SQLAlchemy domain models, deterministic synthetic data, a no-show "
            "prediction pipeline, a RAG subsystem, a structured tool-calling agent, guardrails, escalation "
            "handling, observability, evaluation gates, and a Streamlit demo UI."
        )
    )
    story.append(
        p(
            "The project is local-first: it runs without AWS credentials, paid LLM APIs, or real customer data. "
            "The agent uses a provider-independent LLM interface with a deterministic local provider for tests "
            "and an optional Amazon Bedrock adapter surface for future deployment. The LLM never writes directly "
            "to the database; all actions go through typed Pydantic tools with validation, authorization hooks, "
            "audit logging, confirmation requirements, and idempotency where needed."
        )
    )
    story.append(
        p(
            "The ML component trains reproducible sklearn pipelines for service appointment no-show risk, "
            "compares a logistic regression baseline with a stronger tree-based model, evaluates probability "
            "quality and operational thresholds, serializes model artifacts, and exposes inference through an API. "
            "The strongest part of the repository is that it treats agent behavior as testable software through "
            "deterministic scenarios, safety checks, RAG metrics, release gates, reliability tests, and honest docs."
        )
    )

    story.append(p("2. 5-Minute Technical Walkthrough", "h1"))
    story.append(
        numbered(
            [
                "The API layer is FastAPI-based, with health/readiness endpoints, ML inference, agent execution, and escalation retrieval endpoints.",
                "The data layer uses SQLAlchemy models for synthetic dealership entities including customers, vehicles, appointments, slots, conversations, tool executions, idempotency records, and escalations.",
                "Synthetic data generation creates deterministic dealership data with thousands of customers, vehicles, appointments, service history records, inventory vehicles, slots, and leads.",
                "The ML subsystem builds sklearn pipelines for no-show prediction with preprocessing, leakage controls, calibration diagnostics, threshold analysis, risk tiers, serialized artifacts, and API inference.",
                "The RAG subsystem loads fictional dealership knowledge documents, normalizes and chunks them, embeds them locally, retrieves chunks with citations, and evaluates retrieval quality.",
                "The agent layer is provider-independent. The default provider is deterministic; Bedrock is represented through an optional adapter boundary, not deployed infrastructure.",
                "Tool calling is schema-first. Every tool has metadata, strict schemas, risk level, confirmation requirements, authorization hooks, request IDs, auditing, and structured error responses.",
                "Guardrails include PII redaction, prompt-injection detection, sensitive-topic routing, retrieved-content trust boundaries, tool allowlisting, confirmation enforcement, and fail-closed behavior.",
                "Escalation creates structured packages with reason codes, redacted summaries, attempted tools, retrieved context, outcomes, and recommended next action.",
                "The evaluation lab includes 121 deterministic scenarios, programmatic scorers, JSON/CSV/Markdown reports, and a regression gate runnable from the command line.",
            ]
        )
    )

    qa_rows = [
        ["Likely Question", "Strong Factually Accurate Answer"],
        ["Why separate tools from the LLM?", "The LLM can request actions but cannot directly mutate state. External effects go through typed tools, validation, authorization, transactions, audit logging, and confirmation checks."],
        ["How do you prevent fabricated bookings?", "The agent is tested so it cannot claim success unless the booking tool returns a successful structured result. Tests cover failed bookings and hallucinated transaction success."],
        ["Why deterministic local providers?", "They make tests and evaluations reproducible without paid APIs or AWS credentials, allowing CI to validate orchestration, guardrails, retrieval, and tool behavior."],
        ["What is implemented for Bedrock?", "A provider adapter boundary exists for Amazon Bedrock. Live Bedrock deployment and AWS integration tests are not implemented."],
        ["How is RAG grounded?", "Retrieved chunks include document ID, title, section, chunk ID, score, and source metadata. RAG responses are expected to cite sources and retrieval quality is evaluated deterministically."],
        ["What embedding model is used?", "The default is deterministic local embeddings suitable for tests. Bedrock embeddings, pgvector, and OpenSearch Serverless are future adapter targets."],
        ["How is ML leakage avoided?", "The pipeline excludes outcome fields, post-event timestamps, direct identifiers, synthetic contact hashes, and features unavailable at booking time."],
        ["Why PR-AUC and Brier score?", "Accuracy is weak for no-show prediction. PR-AUC is useful under imbalance, and Brier score evaluates probability calibration for operational risk tiers."],
        ["How are risk bands defined?", "Predicted probabilities map into LOW, MEDIUM, HIGH, and VERY_HIGH tiers, with threshold analysis documenting dealership tradeoffs."],
        ["Why SQLAlchemy repositories?", "They keep database access out of agent/tool code and centralize persistence behavior, transactions, tests, and future database migration."],
        ["How is idempotency handled?", "Booking-style operations use idempotency records so duplicate requests return deterministic responses instead of creating duplicate appointments."],
        ["What happens on provider failure?", "The agent has structured failure behavior and tests for unavailable providers, timeouts, invalid tool calls, unknown tools, and iteration limits."],
        ["How is PII handled?", "The system uses synthetic data only and includes redaction for logs and traces. Tests cover requests to reveal phone numbers or secrets."],
        ["What does observability capture?", "Conversation, LLM calls, retrieval, tool calls, model inference, guardrail decisions, escalation events, correlation IDs, latency, counts, errors, and version metadata."],
        ["Does MLflow require a server?", "No. MLflow integration is optional and supports local development mode without Databricks or a remote MLflow server."],
        ["What is the release gate?", "A command checks version-controlled thresholds for task success, tool selection, transaction consistency, PII safety, escalation recall, RAG hit rate, and hallucinated transaction rate."],
        ["Are evaluation scores production metrics?", "No. They are deterministic local metrics over synthetic scenarios. They are useful regression signals, not proof of live dealership performance."],
        ["What does the UI prove?", "The Streamlit UI demonstrates workflows and observability surfaces over synthetic data; it is not a production staff console."],
        ["Is this production deployed?", "No. It is a production-reference portfolio implementation with Docker and AWS architecture documentation, but no deployed AWS infrastructure."],
        ["What are the key boundaries?", "LLM provider abstraction, retrieval abstraction, typed tools, services/repositories, ML artifacts, guardrails, evaluation, and observability."],
    ]
    story.append(PageBreak())
    story.append(p("3-4. Likely Interview Questions And Strong Answers", "h1"))
    story.append(table(qa_rows, [2.15 * inch, 4.9 * inch]))

    story.append(PageBreak())
    story.append(p("5. Difficult Follow-Up Questions", "h1"))
    story.append(
        numbered(
            [
                "How would the deterministic agent evaluation change when using a real stochastic LLM?",
                "How would you validate no-show model fairness without protected-class labels?",
                "How would you prevent proxy discrimination from features like distance, channel, or loyalty tier?",
                "How would you migrate from SQLite local mode to Aurora PostgreSQL safely?",
                "Where would tenant isolation be enforced for a multi-dealership SaaS version?",
                "How would you implement real identity verification before exposing customer data?",
                "How would you handle stale or contradictory RAG documents?",
                "How would you test Bedrock tool use end-to-end without high CI cost?",
                "How would you detect model drift after deployment?",
                "How would you distinguish low retrieval confidence from low LLM confidence?",
            ]
        )
    )

    tradeoff_rows = [
        ["Weakness An Interviewer May Notice", "Defensible Explanation"],
        ["AWS is documented, not deployed.", "The repository is a local, credential-free portfolio implementation. The AWS mapping is intentionally documented as proposed infrastructure."],
        ["Bedrock, pgvector, OpenSearch, and Knowledge Bases are not live integrations.", "Adapter boundaries keep the local system testable while defining where managed AWS services would fit."],
        ["Evaluation uses a deterministic provider.", "That makes regression testing reliable. Live LLM testing would be an additional evaluation layer, not a replacement."],
        ["Data and model performance are synthetic.", "The project avoids real PII. Metrics demonstrate methodology and engineering discipline, not real dealership predictive validity."],
        ["No Alembic migrations.", "Schema migration was deferred because the project focuses on system behavior, not long-lived database operations."],
        ["Auth, tenant isolation, and identity verification are incomplete.", "The current implementation demonstrates hooks and boundaries; production identity would need an explicit auth layer."],
        ["Local retrieval is not production semantic search.", "The deterministic retriever supports reproducible tests. Production retrieval would use Bedrock embeddings with pgvector or OpenSearch."],
        ["Streamlit is a demo UI.", "It is meant to demonstrate workflows, traces, sources, evaluation results, and escalations over synthetic data."],
    ]
    story.append(p("6-7. Weaknesses And Defensible Tradeoffs", "h1"))
    story.append(table(tradeoff_rows, [2.75 * inch, 4.3 * inch]))

    story.append(p("8. Features Not To Claim Are Implemented", "h1"))
    story.append(
        bullets(
            [
                "Deployed AWS infrastructure or production Bedrock usage.",
                "Live Aurora PostgreSQL, pgvector, OpenSearch Serverless, or Bedrock Knowledge Bases.",
                "Connections to real dealership systems or real customer data.",
                "Real-world no-show model performance or production fairness validation.",
                "Production authentication, tenant isolation, or identity verification.",
                "Live human support ticketing integration.",
                "Production-grade vector infrastructure or verified cloud traffic.",
            ]
        )
    )

    story.append(p("9. Five Strongest Technical Accomplishments", "h1"))
    story.append(
        numbered(
            [
                "A schema-first agent tool layer with validation, confirmation gates, idempotency, audit logging, and transaction safety.",
                "A reproducible predictive ML pipeline with leakage controls, calibration diagnostics, threshold analysis, serialized artifacts, and API inference.",
                "A deterministic RAG subsystem with chunk metadata, citations, retrieval interfaces, and retrieval evaluation.",
                "An agent evaluation laboratory with 121 deterministic scenarios, scorers, reports, and release-gate thresholds.",
                "Clear separation of concerns across API, domain services, repositories, ML, retrieval, guardrails, orchestration, observability, and documentation.",
            ]
        )
    )

    story.append(PageBreak())
    story.append(p("10. System-Design Whiteboard Walkthrough", "h1"))
    story.append(
        p(
            "User / Demo UI -> FastAPI Backend -> Agent Orchestrator<br/>"
            "Agent Orchestrator -> Guardrails -> RAG Retriever -> Knowledge Corpus / Local Vector Store<br/>"
            "Agent Orchestrator -> LLM Provider Interface -> Typed Tool Executor<br/>"
            "Typed Tool Executor -> Domain Services -> Repositories -> SQLite Local / PostgreSQL-Ready<br/>"
            "Typed Tool Executor -> No-Show Risk Service -> Serialized sklearn Pipeline<br/>"
            "Agent Orchestrator -> Human Escalation Service<br/>"
            "All major operations -> Structured Logs / Traces / Evaluation Lab / Regression Gate",
            "mono",
        )
    )
    story.append(
        p(
            "Whiteboard narrative: A user request enters through Streamlit or FastAPI. Guardrails classify sensitive "
            "requests, prompt-injection patterns, and policy concerns. If policy knowledge is needed, the RAG layer "
            "retrieves bounded chunks from the fictional dealership corpus and returns citations. The LLM provider "
            "interface produces structured tool requests. The agent validates the requested tool against an allowlist "
            "and Pydantic schemas. Read-only tools can execute when authorized; write tools require confirmation."
        )
    )
    story.append(
        p(
            "Tools call domain services rather than touching the database directly. Services use repositories backed "
            "by SQLAlchemy. Booking operations use transactions and idempotency records to prevent duplicate side "
            "effects. ML inference is exposed through a service and API endpoint using serialized sklearn artifacts. "
            "Important operations emit structured observability events with correlation IDs and redaction. When the "
            "system hits policy restrictions, tool failures, identity ambiguity, repeated failures, or sensitive "
            "requests, it creates a structured escalation package and returns a customer-safe response."
        )
    )
    story.append(
        p(
            "Interview positioning: The project should be presented as a production-oriented reference architecture "
            "and deterministic portfolio implementation, not as deployed dealership software."
        )
    )

    doc.build(story)


if __name__ == "__main__":
    build()
