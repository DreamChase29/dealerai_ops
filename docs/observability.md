# Observability And MLflow Integration

Phase 11 adds trace-style observability around the production agent boundaries while preserving local
deterministic operation. The default mode emits redacted structured-log spans. MLflow integration is
optional and can run locally without Databricks or a remote tracking server.

## Instrumented Boundaries

The system records spans for:

- conversation orchestration
- LLM calls
- retrieval operations
- typed tool calls
- no-show model inference
- guardrail decisions
- human escalations

Each span includes correlation metadata where available:

- `correlation_id`
- `request_id`
- `conversation_id`

Conversation spans also record:

- total latency
- agent version
- prompt version
- LLM model version
- model-call estimate
- tool-call count
- retrieval count
- final status and error code

Boundary spans record their own latency and relevant deterministic metadata, such as tool name,
tool risk level, guardrail boundary, retrieval document IDs, no-show model version, and escalation
reason.

## Debugging

Use `request_id` as the primary correlation ID when investigating a failed agent response. A single
request should show:

1. a `conversation` span
2. one or more `guardrail_decision` spans
3. optional `retrieval_operation` spans
4. optional `llm_call` spans
5. optional `tool_call` spans
6. optional `model_inference` spans
7. optional `human_escalation` spans

The trace should make it clear whether a failure originated in policy, retrieval, provider output,
tool validation, authorization, transaction execution, or ML inference.

## Production Monitoring

Recommended production dashboards:

- agent request volume by status
- conversation latency p50/p95/p99
- LLM latency and error rate
- retrieval latency and empty-result rate
- tool latency and failure rate by tool name
- guardrail decision counts by violation code
- escalation volume by reason
- no-show inference latency and error rate

Alert candidates:

- provider failure spike
- tool failure spike for transactional tools
- sudden drop in retrieval hit rate from offline evaluations
- PII/safety gate failure
- hallucinated transaction gate failure

## Quality Monitoring

The evaluation lab and release gate produce quality reports under `evaluation/results/`. These reports
should be compared across prompt, tool-schema, model-provider, and retrieval changes. The release gate
is deterministic and should run before deployments. Live-provider evaluations can later emit the same
metadata fields and be compared against this deterministic baseline.

## Cost Monitoring

The evaluation report supports token metadata and estimated cost when a provider supplies input and
output token counts. In local deterministic mode these values remain empty and cost is zero. Production
provider adapters should attach token counts at the LLM-call boundary so cost can be aggregated by:

- environment
- agent version
- prompt version
- model version
- scenario category
- customer workflow

## MLflow

MLflow is optional. The repository does not require a remote MLflow or Databricks account.

Install the optional extra for local development:

```bash
python -m pip install -e ".[observability]"
```

Enable local file-backed tracking:

```bash
DEALERAI_MLFLOW_ENABLED=true
DEALERAI_MLFLOW_TRACKING_URI=file:work/mlruns
DEALERAI_MLFLOW_EXPERIMENT_NAME=dealerai-ops-local
```

When MLflow is enabled and installed, each redacted span is logged as an MLflow run with latency
metrics and safe tags. If MLflow is enabled but the package is absent, the app logs a warning and
continues with non-MLflow telemetry.

## Privacy

Telemetry must not record raw customer PII. The instrumentation avoids raw user messages, raw prompts,
and full tool payload values. Any span attributes that are emitted pass through the shared redaction
helpers before reaching structured logs or MLflow.

Current redaction covers:

- email addresses
- phone numbers
- SSN-like values
- password/API-key/token/credential patterns
- sensitive keys such as `email`, `phone`, `api_key`, `password`, and `token`

Escalation packages and logs should continue to store synthetic identifiers and redacted summaries
rather than unnecessary contact details.

## Trace Retention

Recommended retention policy:

- local development traces: disposable, stored under `work/mlruns` when MLflow is enabled
- CI quality artifacts: retain according to repository artifact policy
- staging traces: short retention for debugging prompt/tool changes
- production traces: retain only as long as needed for support, compliance, and model monitoring

Trace stores must inherit the same access controls as application logs because they can contain
operational metadata, synthetic customer IDs, and error details.
