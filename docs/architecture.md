# Architecture

DealerAI Ops is organized around explicit boundaries between deterministic dealership operations,
predictive ML services, retrieval, and LLM-based reasoning.

## Implemented Scope

Phase 1 provides the production skeleton:

- FastAPI application
- typed configuration
- structured logging
- SQLAlchemy connectivity
- health and readiness endpoints
- tests and developer tooling

Phase 2 adds the synthetic dealership data foundation:

- `Customer`
- `Vehicle`
- `InventoryVehicle`
- `ServiceAppointment`
- `ServiceHistory`
- `ServiceSlot`
- `SalesLead`
- `Conversation`
- `ToolExecution`
- `Escalation`
- deterministic synthetic seed generation
- repository and read-domain service abstractions

Phase 3 adds the production-oriented no-show prediction component:

- leakage-audited feature extraction from synthetic appointments, customers, and vehicles
- sklearn preprocessing pipelines shared by training and inference
- logistic regression baseline
- calibrated histogram gradient boosting candidate
- validation/test metrics and threshold analysis
- serialized model, feature schema, metrics, metadata, timestamp, and dataset fingerprint
- `POST /ml/no-show/predict`

Phase 4 adds the typed tool layer:

- strict Pydantic input/output schemas
- deterministic execution without an LLM
- authorization hook
- structured errors
- request IDs
- audit records
- confirmation gates for important writes
- idempotency records for booking-style operations
- transactional appointment, lead, and escalation operations

Phase 5 adds the retrieval subsystem:

- synthetic dealership knowledge corpus under `/knowledge`
- document loading and normalization
- section-aware chunking
- citation-ready metadata
- embedding, vector store, and reranking interfaces
- deterministic local hashing embeddings and in-memory vector store
- future adapter surfaces for Bedrock embeddings, Aurora PostgreSQL pgvector, and OpenSearch Serverless
- retrieval evaluation data and Recall@K, MRR, Hit Rate@K metrics

Phase 6 adds provider-independent LLM agent orchestration:

- explicit conversation state
- deterministic local provider for offline tests
- optional Amazon Bedrock provider adapter
- optional retrieval before model reasoning
- structured tool requests and final responses
- confirmation workflow for transactional tools
- iteration and timeout controls
- structured agent failures
- guardrails against fabricated transaction success
- `POST /agent/run`

Phase 7 adds guardrails and policy enforcement:

- PII and secret redaction for structured logs
- prompt-injection indicator blocking
- tool allowlisting before provider-requested tool execution
- retrieved-content trust boundary checks
- sensitive-topic fail-closed routing
- maximum retrieval context enforcement
- adversarial tests for unsafe user and retrieved-document inputs

Phase 8 adds the human escalation subsystem:

- structured escalation reasons
- redacted escalation packages
- customer-safe escalated agent responses
- escalation package persistence on escalation records
- demo read APIs at `GET /escalations` and `GET /escalations/{id}`

Phase 9 adds the Agent Evaluation Laboratory:

- 121 deterministic scenarios across normal customer, multi-turn, tool-selection, tool-argument,
  RAG, transaction, tool-failure, human-escalation, PII/safety, prompt-injection, and historical
  regression categories
- scripted local provider execution through the production agent orchestrator
- programmatic scorers for task success, tool usage, argument accuracy, transactions, retrieval,
  citations, PII leakage, escalation, policy violations, and hallucinated transactions
- latency, model-call, tool-call, retrieval, token metadata, and estimated-cost capture
- JSON, CSV, and Markdown reports under `evaluation/results`

Phase 10 adds AI regression and release gates:

- committed threshold configuration in `evaluation/quality_thresholds.json`
- `python -m evaluation.gate` release decision command
- gate metrics for task success, tool selection, transaction consistency, PII safety,
  hallucinated transactions, required escalation, and RAG retrieval
- human-readable `quality_gate.md` and machine-readable `quality_gate.json`
- CI execution of tests, deterministic evaluations, regression gate, and quality report artifact
  upload

Phase 11 adds observability and optional MLflow integration:

- redacted spans for conversations, LLM calls, retrieval operations, tool calls, model inference,
  guardrail decisions, and human escalations
- correlation IDs propagated from request IDs through nested spans
- latency, count, error, agent-version, prompt-version, and model-version attributes
- structured-log telemetry by default
- optional local MLflow tracking with `file:work/mlruns`
- privacy-preserving trace payloads that avoid raw prompts, user messages, and full tool payloads

Phase 12 adds a Streamlit portfolio demonstration UI:

- multi-page demo console for the assistant, Customer 360, inventory, service operations, no-show
  risk, traces, RAG sources, evaluations, escalations, and architecture
- deterministic local assistant scenarios backed by the production orchestrator, tool executor,
  RAG retriever, guardrails, and synthetic data
- visible tool activity, retrieved citations, confirmation requests, and final outcomes
- operational trace display that excludes hidden chain-of-thought and sensitive raw payloads

Phase 13 adds AWS production deployment design documentation:

- proposed mapping to Amazon Bedrock, Bedrock tool use, S3, AWS Lambda, API Gateway, Aurora
  PostgreSQL, pgvector, Bedrock Knowledge Bases, CloudWatch, IAM, and Secrets Manager
- OpenSearch Serverless documented as an alternative vector retrieval backend
- network/security boundaries, least-privilege IAM, secret management, PII handling, database access,
  tool execution boundaries, observability, failure handling, scaling, cost, deployment, and rollback
  guidance
- standalone Mermaid source at `docs/architecture/aws-production.mmd`
- no deployed AWS infrastructure or credential requirement

Phase 14 adds reliability and chaos/failure scenario coverage:

- controlled tests for LLM unavailability/timeouts, vector retrieval failures, database failures,
  tool timeouts/500s, duplicate writes, partial transactions, poor retrieval, malformed model tool
  calls, hallucinated tools, prompt injection, PII requests, iteration limits, unavailable ML service,
  and corrupt model artifacts
- explicit customer-facing response classes, retry guidance, escalation expectations, logging
  requirements, and data-integrity requirements
- graceful handling for provider timeouts, retrieval failures, and corrupt no-show model artifacts

Production LLM prompt hardening is reserved for later phases.

## Target Boundaries

```text
api/
  HTTP endpoints and request/response models

core/
  settings, logging, errors, shared infrastructure

observability/
  correlation context, redacted spans, structured-log telemetry, and optional MLflow sink

db/
  database engine/session setup, ORM models, and future migrations

domain/
  dealership enums, synthetic data, repositories, and pure domain services

tools/
  typed, validated, audited operations exposed to future agents

agents/
  orchestration, provider adapters, guardrails, escalation policies

escalations/
  human handoff package schemas and services

rag/
  corpus loading, normalization, chunking, retrieval, citations, and retrieval evaluation

ml/
  no-show feature extraction, training, evaluation, serialization, and inference

evals/
  regression tests for agents, RAG, safety, and ML behavior

ui/
  Streamlit portfolio demo and deterministic demo data adapters
```

## Design Principles

- Domain logic must not depend on LLM provider behavior.
- LLMs must never write directly to the database.
- External actions must pass through typed tools.
- Important writes require explicit confirmation.
- Local execution must not require AWS credentials or real customer data.
- Cloud dependencies should be replaceable through interfaces/adapters.
- Agents may reason, but all operational actions must flow through validated typed tools.
- Retrieved documents provide evidence, not instructions that can override system or tool policies.

## Synthetic Data Policy

The domain dataset is synthetic and deterministic. Customer rows contain operational and behavioral
features useful for future no-show modeling, such as distance to dealership, acquisition channel,
loyalty tier, preferred contact method, prior no-show count, completed appointment count, booking
channel, lead time, reminder count, and appointment type. It intentionally avoids protected-class
features and real PII.

## Persistence Model

The ORM uses string IDs with stable prefixes, foreign keys for core relationships, check constraints
for date and numeric validity, uniqueness constraints for identifiers such as VINs and stock numbers,
and indexes on common lookup and analytics fields. SQLite is used for deterministic local tests, while
PostgreSQL URLs are supported through SQLAlchemy and `psycopg`.
