# Human Escalation Design

## Scope

Phase 8 adds a structured human escalation subsystem for the demo application. Escalation is a
handled customer outcome, not an internal crash path. When the agent cannot safely or reliably
continue, it creates a redacted package for dealership staff and returns an appropriate customer-facing
response.

## Structured Reasons

Escalations use `EscalationReason`:

- `LOW_CONFIDENCE`
- `TOOL_FAILURE`
- `CUSTOMER_REQUEST`
- `POLICY_RESTRICTION`
- `IDENTITY_AMBIGUITY`
- `REPEATED_FAILURE`
- `SENSITIVE_REQUEST`
- `SAFETY_CONCERN`

Legacy synthetic reason strings are mapped into these structured reasons when old demo records are
read.

## Escalation Package

Each package contains:

- conversation ID
- authenticated customer identifier when supplied by the caller
- structured reason
- brief redacted conversation summary
- relevant retrieved information
- tools attempted
- individual tool outcomes
- recommended next action
- timestamp

The package is persisted as JSON on the `escalations.package_payload` column and returned through
agent responses and demo read APIs.

## Trigger Points

The Phase 8 agent escalates for:

- explicit customer request for a human, representative, manager, advisor, or callback
- identity ambiguity indicators
- sensitive or policy-restricted guardrail decisions
- provider failure / low-confidence model availability
- sensitive write-tool failures
- repeated tool failures
- model attempts to fabricate transactional success

Read-only validation failures can still be returned as normal structured tool failures when no human
handoff is needed.

## Customer Response

Escalated runs return `AgentStatus.ESCALATED` and a plain customer-facing response such as:

```text
I couldn’t complete that action automatically, so I’ve routed it to a human team.
```

The customer does not receive raw stack traces, internal exception names, secret values, or internal
policy details.

## PII Minimization

The system only includes `authenticated_customer_id` in the package when the API caller provides it
explicitly. The agent does not infer identity from free-form text. Conversation summaries, retrieved
excerpts, and tool error messages pass through redaction before package creation.

## Demo APIs

The demo app exposes:

- `GET /escalations`
- `GET /escalations/{id}`

These endpoints return structured `EscalationRecord` objects and do not expose unnecessary PII.

## Current Limitations

- Packages are stored as JSON on the escalation row rather than a dedicated workflow table.
- Assignment and resolution workflows are read-only in this phase.
- Authentication is represented by an explicit `authenticated_customer_id` request field; real authn
  and tenant isolation are future work.
- Escalation summaries are deterministic excerpts, not LLM-generated summaries.
- Demo APIs assume database tables have been created by tests, seed scripts, or a future migration
  runner.
