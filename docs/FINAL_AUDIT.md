# Final Audit

Audit date: 2026-08-12

DealerAI Ops is a production-oriented portfolio implementation for a simulated automotive dealership.
This audit reviews what is actually implemented, what was verified, and what remains design-only.

## Audit Scope

Reviewed:

- architecture and module boundaries
- code quality and Python typing
- security and PII handling
- data leakage and ML train/test methodology
- model evaluation and thresholding
- RAG architecture and citation behavior
- typed tool schemas and transaction safety
- agent failure modes and guardrails
- human escalation
- evaluation methodology and regression gates
- tests and CI
- documentation and README credibility
- Docker and Docker Compose configuration
- dependency hygiene
- dead code, duplicate code, placeholder text, hardcoded secrets, and unverified claims
- logging and observability

## Implemented Capabilities

Application foundation:

- FastAPI application factory.
- `GET /health` and `GET /ready`.
- Environment-based settings with no required local secrets.
- Structured logging and redaction hooks.
- Dockerfile and Docker Compose for local API/Postgres operation.
- Makefile developer commands.
- GitHub Actions workflow for lint, format check, type check, tests, deterministic evaluations, and
  release gate.

Data and persistence:

- SQLAlchemy ORM model covering `Customer`, `Vehicle`, `InventoryVehicle`,
  `ServiceAppointment`, `ServiceHistory`, `ServiceSlot`, `SalesLead`, `Conversation`,
  `ToolExecution`, `ToolIdempotencyRecord`, and `Escalation`.
- PostgreSQL-compatible configuration and SQLite local/test fallback.
- Deterministic synthetic dealership data generator.
- Repository and domain service layer.
- Referential integrity and uniqueness tests.

Predictive ML:

- Reproducible sklearn no-show prediction pipeline.
- Logistic regression baseline and calibrated tree-based model candidate.
- Leakage-aware feature extraction.
- Train/validation/test split.
- ROC-AUC, average precision, precision, recall, F1, Brier score, confusion matrix, calibration
  diagnostics, and threshold analysis.
- Serialized model, preprocessing pipeline, feature schema, metadata, metrics, timestamp, and dataset
  fingerprint.
- Operational risk tiers: `LOW`, `MEDIUM`, `HIGH`, `VERY_HIGH`.
- `POST /ml/no-show/predict`.

Agentic AI:

- Provider-independent LLM interface.
- Deterministic local provider for test/demo mode.
- Amazon Bedrock provider adapter surface.
- Explicit conversation state.
- Structured model responses: final answer or tool request.
- Maximum tool iteration controls and timeout handling.
- Structured failure responses.
- No arbitrary Python/code execution tools.

Typed tools:

- Strict Pydantic input/output schemas.
- Tool metadata with name, description, risk level, confirmation requirement, input schema, and
  output schema.
- Authorization hook.
- Request IDs and audit records.
- Confirmation gates for transactional writes.
- Idempotency records for booking-style operations.
- Transaction rollback behavior for failed writes.
- No direct LLM database access.

RAG:

- Synthetic dealership knowledge corpus.
- Document loading, normalization, section-aware chunking, metadata, deterministic local embeddings,
  vector store interface, retrieval, optional reranking interface, and citations.
- Retrieval evaluation data with known relevant documents.
- Recall@K, MRR, and Hit Rate@K evaluation.
- Future adapter surfaces for Bedrock embeddings, Aurora PostgreSQL pgvector, and OpenSearch
  Serverless.

Guardrails and security:

- PII and secret redaction helpers.
- Prompt-injection indicators.
- Tool allowlisting.
- Retrieved-content trust boundary checks.
- Confirmation-bypass blocking.
- Sensitive request routing.
- Fail-closed behavior for unsafe operations.

Human escalation:

- Structured escalation reasons.
- Redacted escalation package creation.
- Customer-safe escalation responses.
- Demo escalation read APIs.

Evaluation and release gate:

- 121 deterministic agent evaluation scenarios.
- Programmatic scorers for task success, tool selection, tool arguments, transaction consistency,
  retrieval hit, citation presence/correctness, PII leakage, escalation behavior, policy violation,
  and hallucinated transactions.
- JSON, CSV, and Markdown evaluation reports.
- Configured quality thresholds in version-controlled JSON.
- `python -m evaluation.gate` exits non-zero on configured regression failure.

Observability:

- Redacted spans for conversation, LLM call, retrieval operation, tool call, model inference,
  guardrail decision, and human escalation.
- Correlation IDs, request IDs, conversation IDs, latency, counts, errors, agent version, prompt
  version, and model version.
- Optional local MLflow telemetry sink.

Reliability:

- Controlled tests for provider failures, retrieval failures, database failures, tool timeouts,
  upstream errors, duplicate bookings, partial transaction rollback, malformed tool calls,
  hallucinated tool names, prompt injection, PII requests, iteration limits, unavailable ML service,
  and corrupt model artifacts.
- Documented response classes, retry guidance, escalation expectations, logging requirements, and
  data-integrity requirements.

Portfolio demonstration:

- Streamlit demo UI with assistant, Customer 360, inventory, appointments, no-show risk, operational
  trace, RAG sources, evaluation dashboard, human escalations, and architecture views.

AWS production mapping:

- Documentation-only mapping to Amazon Bedrock, Bedrock tool use, S3, AWS Lambda, API Gateway,
  Aurora PostgreSQL, pgvector, Bedrock Knowledge Bases, CloudWatch, IAM, Secrets Manager, and
  OpenSearch Serverless as an alternative vector backend.

## Issues Fixed During Final Audit

- Dockerfile now copies the `knowledge/` corpus required by the default agent retriever.
- CI now runs `ruff format --check src tests`.
- Makefile now includes `format-check` and the aggregate `check` target runs it.
- Docker Compose database credentials now use environment substitution with local-only defaults.
- Docker Compose Postgres healthcheck now uses the configured container database/user variables.
- Streamlit was moved out of core runtime dependencies into `ui` and `dev` extras.
- Removed the placeholder project homepage from package metadata.

## Verification Performed

Commands run during this audit:

```bash
rg risk-marker scan for TODO/FIXME/stub markers, placeholders, fake metrics, hardcoded secrets,
and overclaiming language
rg sensitive-term scan for password/API-key/secret/token references
ruff check src tests
ruff format --check src tests
mypy
pytest
python -m evaluation.run
python -m evaluation.gate
```

Additional manual inspection:

- `README.md`
- `pyproject.toml`
- `.github/workflows/test.yml`
- `Dockerfile`
- `docker-compose.yml`
- `.env.example`
- `.pre-commit-config.yaml`
- architecture, ML, RAG, security, observability, reliability, AWS, and release-gate docs

## Test Counts And Results

Latest full local test result during audit:

- pytest tests: 111 passed
- warnings: 85, all from dependency deprecations observed in `fastapi.testclient`/Starlette and
  `joblib`/NumPy interactions
- coverage summary: 84% total line coverage

Static checks:

- Ruff lint: passed
- Ruff formatter check: passed
- mypy strict package check: passed for 70 source files

Docker checks:

- Dockerfile inspected and corrected to include the knowledge corpus.
- Docker Compose inspected and corrected for configurable local database credentials and healthcheck.
- `docker compose config --quiet` completed with a valid configuration result; Docker also emitted a
  warning that it could not read the user-level `C:\Users\wilfr\.docker\config.json`.
- No live Docker build or container startup is required for local correctness and was not treated as
  evidence of deployed infrastructure.

## Evaluation Results

Latest deterministic evaluation report:

- scenarios: 121
- passed scenarios: 121
- failed scenarios: 0
- pass rate: 1.0
- average latency: approximately 69.45 ms
- model calls: 157
- tool calls: 103
- retrieval count: 115
- estimated cost: 0.0 USD in deterministic local mode

Release gate:

- status: accepted
- threshold version: `phase10-defaults-2026-08-11`
- task success: 1.0000
- tool selection accuracy: 1.0000
- transaction consistency: 1.0000
- PII safety pass rate: 1.0000
- required escalation recall: 1.0000
- RAG retrieval hit rate: 1.0000
- hallucinated transaction rate: 0.0000

These are deterministic local evaluation results, not claims about live production performance.

## Search Findings

Expected and acceptable findings:

- `NotImplementedError` appears in future adapter classes for Bedrock embeddings, Aurora pgvector,
  and OpenSearch Serverless. These are intentionally explicit adapter stubs and are documented as not
  implemented.
- `placeholder` appears in README screenshot placeholders and fictional knowledge-base text such as
  loaner agreement placeholder language.
- `password`, `secret`, `token`, and `api_key` appear in guardrail tests, redaction tests,
  documentation, and redaction logic.
- Evaluation result files contain adversarial prompt text and empty token metadata from local
  deterministic mode.

No hardcoded production secrets were identified.

## Known Limitations

- The system uses synthetic data only.
- It is not connected to real dealership CRMs, DMS systems, scheduling providers, or payment systems.
- Authentication, identity verification, and tenant isolation are not production-implemented.
- Database migration tooling is not present.
- AWS infrastructure is documented but not provisioned.
- Bedrock integration is an adapter surface, not an exercised live AWS integration.
- Bedrock Knowledge Bases, pgvector, and OpenSearch Serverless adapters are not implemented.
- Streamlit is a portfolio demo UI, not a production staff console.
- Runtime retrieval relevance confidence is basic and relies primarily on deterministic evaluation.
- Retry/backoff/circuit-breaker behavior is documented, but not implemented as reusable middleware.
- Tool timeout checks in the deterministic local executor occur after handler return; production
  external adapters should enforce hard network timeouts.
- Evaluation scenarios are deterministic and synthetic; they do not prove behavior under live model
  drift or real user traffic.
- Fairness analysis is documented as necessary before real-world use, especially for proxy features
  such as distance, channel, and loyalty tier.

## Not-Implemented Production Components

- Infrastructure as code.
- Real AWS deployment.
- Production authentication and authorization provider integration.
- Secrets Manager secret creation and rotation.
- Alembic or equivalent schema migrations.
- RDS Proxy configuration.
- Bedrock Converse tool-use integration tests with mocked AWS clients.
- Bedrock Knowledge Base ingestion pipeline.
- Aurora pgvector schema and vector indexes.
- OpenSearch Serverless collection/index configuration.
- CloudWatch dashboards and alarms.
- Production incident runbooks.
- Production cost dashboards.
- Real customer data governance workflow.
- Model drift monitoring on matured real appointments.

## Recommended Future Work

1. Add Alembic migrations for all SQLAlchemy models.
2. Add Terraform or AWS CDK skeletons for the documented AWS production-reference architecture.
3. Implement production authn/authz and role-based tool authorization.
4. Add retry/backoff/circuit-breaker adapters for Bedrock, vector retrieval, database, and external
   operational APIs.
5. Implement pgvector and OpenSearch Serverless adapters behind the existing vector-store interface.
6. Add mocked Bedrock Converse tool-use integration tests.
7. Add screenshot regression tests and real screenshots for the Streamlit demo.
8. Add CI jobs that build the Docker image and validate Docker Compose config.
9. Add model drift simulation and retraining workflow tests.
10. Add fairness and subgroup monitoring design before any real-world dealership deployment.

## Final Assessment

DealerAI Ops is an honest, production-oriented portfolio implementation. It demonstrates senior-level
architecture and engineering patterns for AI systems: separation between LLM reasoning and domain
actions, typed tool execution, leakage-aware ML, deterministic RAG/evaluation, guardrails, escalation,
observability, reliability testing, and AWS-ready design boundaries.

It should not be represented as deployed in production or integrated with real dealership systems.
Its strongest claim is that it is a well-tested local/reference implementation showing how such a
system could be built and evaluated responsibly.
