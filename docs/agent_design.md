# Agent Design

## Scope

Phase 6 adds LLM orchestration without adding autonomous database writes. The agent coordinates
conversation state, optional retrieval, provider-independent model responses, strict tool calls,
confirmation gates, and structured failures.

## Provider Boundary

`dealerai_ops.agents.providers.LLMProvider` is the model interface. Providers return one of two
validated objects:

- `ToolRequest`: a registered tool name plus JSON-like arguments.
- `FinalResponse`: a final user-facing message.

The default `RuleBasedLocalLLMProvider` is deterministic and requires no paid API access. It exists
for local development and tests, not as a production-grade language model. `ScriptedLLMProvider` and
`FailingLLMProvider` support regression tests.

`BedrockLLMProvider` is an optional Amazon Bedrock adapter. It imports `boto3` only when selected and
wraps malformed provider output or invocation failures in `LLMProviderError`.

## Agent Loop

One `AgentRunRequest` represents a single user turn:

1. Append the user message to explicit `ConversationState`.
2. Infer a lightweight deterministic intent for state metadata.
3. Retrieve knowledge chunks when the user asks a policy, warranty, maintenance, privacy, FAQ, or
   escalation-style question.
4. Apply retrieved-content trust-boundary checks.
5. Ask the configured provider for a structured response using only allowlisted tool metadata.
6. Validate tool names against the registry and allowlist.
7. Force model-requested transactional tools into an unconfirmed state.
8. Execute tools only through `ToolExecutor`.
9. Append structured tool results to state.
10. Pause with `REQUIRES_CONFIRMATION` when a tool requires explicit confirmation.
11. On a later confirmed request, execute the pending tool with `confirmed=true`.
12. Continue until a final response, provider failure, timeout, policy failure, or iteration limit.

The agent never exposes arbitrary Python or code execution. The only executable operations are typed
tool definitions registered in `dealerai_ops.tools`.

Phase 7 guardrails add prompt-injection checks, sensitive-topic fail-closed routing, tool
allowlisting, maximum retrieval context, and retrieved-content policy-injection detection. See
`docs/security.md`.

Phase 8 escalations convert selected low-confidence, policy, safety, identity, customer-requested,
and sensitive tool-failure paths into `AgentStatus.ESCALATED` responses with a structured human
handoff package. See `docs/escalation_design.md`.

## Confirmation Workflow

Model output is not allowed to self-confirm writes. If a provider includes `"confirmed": true` in a
first-pass transactional tool request, the orchestrator overrides it to `false`. The pending
`ToolRequest` is stored in `ConversationState.pending_confirmation`.

A write executes only when the next `AgentRunRequest` includes:

- the prior state with a pending confirmation
- `confirmed=true`

The tool layer still enforces its own confirmation schema, validation, authorization, transaction,
audit, and idempotency behavior.

## Transaction Truthfulness Guardrail

The orchestrator rejects final answers that claim transactional success unless the latest relevant
transactional tool result has `outcome="succeeded"`. This prevents a provider from saying an
appointment was booked, canceled, rescheduled, a lead was created, or a human handoff succeeded when
the tool did not return success.

## Structured Failures

Agent failures use `AgentRunResult.status="failed"` plus `AgentError`:

- `PROVIDER_FAILURE`
- `TOOL_TIMEOUT`
- `ITERATION_LIMIT`
- `INVALID_MODEL_OUTPUT`
- `UNKNOWN_TOOL`

Tool-level validation, authorization, execution, and idempotency conflicts remain structured
`ToolCallResult` objects inside conversation state.

## Retrieval And Citations

When retrieval runs, retrieved chunks are stored in state and successful agent responses include
citation objects with:

- `document_id`
- `title`
- `section`
- `chunk_id`
- `source_path`

This keeps RAG answer references machine-checkable for future groundedness and citation-correctness
evaluation.

## Timeouts And Iteration Limits

The orchestrator enforces:

- `agent_max_tool_iterations`
- `agent_timeout_seconds`
- per-tool elapsed-time checks

Current local execution is synchronous, so timeout checks are deterministic deadline checks around
provider/tool calls rather than process-level cancellation. Future production workers should add
interruptible execution around network providers and long-running external tools.

## Current Limitations

- The local provider is rule-based and intentionally simple.
- Bedrock prompt/response formatting is a minimal adapter surface and will need provider-specific
  hardening before production.
- Agent evaluation datasets are not implemented yet.
- Conversation state is passed explicitly but not persisted as a durable transcript table yet.
- Tool execution uses the existing synchronous SQLAlchemy session.
