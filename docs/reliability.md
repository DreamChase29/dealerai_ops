# Reliability And Failure Scenarios

Phase 14 defines controlled reliability behavior for DealerAI Ops. The goal is graceful degradation:
never fabricate transactional success, never bypass confirmation, never leak PII, and preserve data
integrity when dependencies fail.

## System-Wide Reliability Principles

- Fail closed for sensitive operations.
- Escalate when the system cannot safely complete a customer request.
- Retry only idempotent or read-only operations, and only with bounded attempts.
- Do not retry non-idempotent writes unless an idempotency key is present and persisted.
- Preserve transaction integrity with rollback on failed writes.
- Log structured, redacted failure metadata with request ID, conversation ID where available, tool
  name where available, and failure code.
- Return customer-safe response classes instead of raw internal exceptions.

## Customer-Facing Response Classes

| Response class | Meaning |
| --- | --- |
| `SAFE_RETRYABLE_FAILURE` | The system could not complete a read or transient operation; a retry may be appropriate. |
| `SAFE_NON_RETRYABLE_FAILURE` | The request is invalid, unsafe, or unsupported; retrying unchanged is not useful. |
| `CONFIRMATION_REQUIRED` | A write action is paused until explicit user confirmation is supplied. |
| `ESCALATED_TO_HUMAN` | The system routed the conversation to a human team with a redacted package. |
| `GROUNDING_UNAVAILABLE` | Retrieval did not provide adequate sources; the answer must avoid unsupported claims. |
| `TRANSACTION_REPLAYED` | A duplicate idempotent write returned the original successful result without a second write. |

## Failure-Mode Table

| Failure mode | Expected system behavior | Retry appropriate | Escalation | Customer-facing response class | Logging requirements | Data-integrity requirement | Automated coverage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LLM unavailable | Catch provider failure and route to human review. | Yes, bounded provider retry before escalation in production. | Yes, `LOW_CONFIDENCE`. | `ESCALATED_TO_HUMAN` | `llm_call` error span, request ID, provider code, no raw PII. | No tools execute after provider failure. | `tests/test_reliability.py` |
| LLM timeout | Catch timeout separately from generic provider failure. | Yes, bounded retry with timeout budget. | Yes, `LOW_CONFIDENCE`. | `ESCALATED_TO_HUMAN` | `llm_call` timeout/error span and latency. | No transaction may be claimed or executed from incomplete model output. | `tests/test_reliability.py` |
| Vector store unavailable | Stop RAG flow and escalate knowledge request. | Yes, bounded retrieval retry for read-only knowledge queries. | Yes, `LOW_CONFIDENCE`. | `ESCALATED_TO_HUMAN` | Retrieval failure code, top-k, request ID, no raw document dumps. | No writes occur because retrieval failed. | `tests/test_reliability.py` |
| Database unavailable | Return structured tool failure; do not claim success. | Yes for read-only operations; writes require idempotency and state inspection. | If repeated or write-related. | `SAFE_RETRYABLE_FAILURE` or `ESCALATED_TO_HUMAN` | Tool error code, database operation class, audit failure if audit cannot persist. | Roll back session; no partial writes. | `tests/test_reliability.py` |
| Tool API timeout | Fail closed after configured tool timeout. | Yes for read-only external calls; writes require idempotency. | Usually no for one read timeout; yes after repeated failures or write uncertainty. | `SAFE_RETRYABLE_FAILURE` | `tool_call` span with timeout code and latency. | No success result when elapsed time exceeds timeout. | `tests/test_reliability.py` |
| Tool API 500 | Return deterministic structured tool error. | Yes when upstream is idempotent or read-only. | Yes for repeated failures or sensitive write failures. | `SAFE_RETRYABLE_FAILURE` | `tool_call` error span and structured upstream failure code. | Roll back any local transaction tied to the failed tool. | `tests/test_reliability.py` |
| Duplicate booking request | Replay idempotent result if payload hash matches; reject conflicts. | Yes with same idempotency key and same payload. | No for clean replay; yes for unresolved conflict. | `TRANSACTION_REPLAYED` | Tool audit includes idempotency key and replay flag. | Exactly one appointment and one capacity reservation. | `tests/test_reliability.py`, `tests/test_tools.py` |
| Partially completed transaction | Roll back all writes and return failure. | Only with idempotency and after confirming transaction state. | Yes when customer-impacting write state is uncertain. | `ESCALATED_TO_HUMAN` or `SAFE_RETRYABLE_FAILURE` | Tool failure and rollback metadata; audit if database available. | No orphaned records or capacity drift. | `tests/test_reliability.py` |
| Retrieval returns zero results | Complete only with a no-source response or ask for clarification; citations remain empty. | Retry with reformulated query if customer intent is still answerable. | No by default; yes if policy answer is required for a sensitive decision. | `GROUNDING_UNAVAILABLE` | Retrieval count zero and query length, no raw sensitive prompt. | No writes occur based on missing evidence. | `tests/test_reliability.py` |
| Retrieval returns irrelevant results | Preserve citations and avoid unsupported claims; evaluation should catch quality regressions. | Retry/rerank may be appropriate. | No by default; yes for high-impact policy questions. | `GROUNDING_UNAVAILABLE` | Retrieved document IDs, scores, and answer confidence metadata. | No transactional decision should depend only on irrelevant retrieval. | `tests/test_reliability.py` |
| Malformed model tool arguments | Pydantic validation rejects arguments and returns structured tool error. | No unless the model can repair arguments within iteration limits. | No for one read-only validation error; yes after repeated failures. | `SAFE_NON_RETRYABLE_FAILURE` | Validation error code with redacted schema error details. | Tool handler does not execute. | `tests/test_reliability.py`, `tests/test_agent_orchestration.py` |
| Hallucinated tool name | Reject unknown tool before execution. | No. | No by default; yes if repeated or suspicious. | `SAFE_NON_RETRYABLE_FAILURE` | Unknown tool name and request ID. | No tool execution or database mutation. | `tests/test_reliability.py`, `tests/test_agent_orchestration.py` |
| Prompt injection | Guardrail blocks before retrieval, model, or tools when detected in user input. | No. | Yes, `SAFETY_CONCERN` or policy restriction. | `ESCALATED_TO_HUMAN` | Guardrail code, request ID, redacted input metadata. | No tool execution. | `tests/test_reliability.py`, `tests/test_agent_guardrails.py` |
| PII request | Guardrail blocks bulk/private PII disclosure. | No. | Yes, `SENSITIVE_REQUEST`. | `ESCALATED_TO_HUMAN` | Guardrail code and redacted metadata only. | No bulk customer data export. | `tests/test_reliability.py`, `tests/test_agent_guardrails.py` |
| Agent infinite-loop attempt | Stop at maximum tool iterations and return structured failure. | No unless operator changes prompt/tool policy after investigation. | No by default; yes after repeated failure. | `SAFE_NON_RETRYABLE_FAILURE` | Iteration limit code, model/tool call counts, request ID. | No additional tools after limit. | `tests/test_reliability.py`, `tests/test_agent_orchestration.py` |
| ML model unavailable | Return structured prediction-tool failure if no model service is configured. | Yes after model service health check or artifact reload. | Yes when needed for service scheduling decision. | `SAFE_RETRYABLE_FAILURE` | `model_inference` or tool error code, model version if known. | Do not invent probability or risk tier. | `tests/test_reliability.py` |
| Corrupt model artifact | Raise model artifact error and return API 503. | Yes after artifact rollback or redeploy. | Not directly; caller may escalate customer workflow. | `SAFE_RETRYABLE_FAILURE` | Model artifact path/class, no artifact contents. | Do not serve predictions from corrupt artifacts. | `tests/test_reliability.py` |

## Retry Guidance

Recommended retry behavior for production adapters:

- LLM calls: retry transient provider failures with exponential backoff and jitter within the agent
  request timeout. Do not retry malformed provider output indefinitely.
- Retrieval: retry unavailable vector store calls for read-only knowledge requests. If retries fail,
  return grounding unavailable or escalate.
- Tool APIs: retry read-only calls. Retry writes only when the tool has an idempotency key and the
  transaction state can be proven.
- Database: retry short transient read failures at the repository or infrastructure layer. For writes,
  rely on database transactions and idempotency records.
- ML inference: retry artifact reload or switch to the last known good artifact only when version
  compatibility is explicit.

## Logging And Observability

Every controlled failure should emit structured, redacted telemetry:

- `conversation`: status, model calls, tool calls, retrieval count, error code.
- `llm_call`: provider/model version, latency, timeout or provider failure code.
- `retrieval_operation`: top-k, retrieval count, document IDs when available.
- `tool_call`: tool name, risk level, confirmation requirement, outcome, idempotency replay flag,
  error code.
- `model_inference`: model family, model version, latency, error code.
- `guardrail_decision`: boundary, decision, violation code.
- `human_escalation`: reason, escalation ID, conversation/request correlation.

Logs and traces must redact PII and secret-like values before emission.

## Data Integrity Checks

Reliability tests assert these invariants:

- Duplicate bookings create only one appointment.
- Failed partial writes roll back inserted records.
- Confirmation-required writes do not mutate state.
- Unknown tools and malformed arguments do not execute handlers.
- Provider, retrieval, prompt-injection, and PII failures do not execute tools.
- Corrupt ML artifacts do not return probabilities or risk tiers.

## Known Limitations

- Current retries are documented design guidance; the local deterministic runtime generally performs
  one attempt and fails safely.
- Runtime retrieval relevance is not yet scored by a production reranker or confidence model; the
  evaluation lab catches deterministic retrieval quality regressions.
- Tool timeout checks happen after local handler return in the deterministic executor. Production
  external adapters should enforce hard network timeouts around remote calls.
