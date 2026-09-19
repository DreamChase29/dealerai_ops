# Typed Tool Architecture

## Purpose

Phase 4 added an LLM-independent tool layer for dealership operations. The tools are deterministic,
typed, validated, authorized, audited, and transaction-aware. Phase 6 agents use this layer rather
than writing directly to the database.

## Tool Boundary

Future agents must call external actions only through registered tools. Tools do not construct SQL
queries directly; they call domain services, which use repositories for persistence.

```text
agent / API / tests
  -> ToolExecutor
    -> Pydantic validation
    -> authorization hook
    -> confirmation gate
    -> idempotency replay check
    -> domain service / ML service
    -> repository layer
    -> audit + commit
```

## Risk Classes

| Class | Use |
| --- | --- |
| `READ_ONLY` | Data lookup or prediction with no mutation |
| `LOW_RISK_WRITE` | Low-impact writes such as creating a sales lead |
| `HIGH_RISK_WRITE` | Appointment booking, rescheduling, and cancellation |
| `ESCALATION` | Human handoff/escalation operations |

## Registered Tools

- `lookup_customer`
- `get_customer_vehicle`
- `get_service_history`
- `search_inventory`
- `get_vehicle_details`
- `get_available_service_slots`
- `predict_no_show_risk`
- `book_service_appointment`
- `reschedule_service_appointment`
- `cancel_service_appointment`
- `create_sales_lead`
- `handoff_to_human`

Each tool exposes metadata:

- name
- description
- risk level
- confirmation requirement
- JSON input schema
- JSON output schema

## Validation

All tool inputs and outputs use strict Pydantic schemas. Unknown input fields are rejected. Validation
errors return structured `ToolCallResult` responses with code `VALIDATION_ERROR`.

## Authorization

The executor accepts a `ToolAuthorizer` hook. The default local implementation allows all calls for
deterministic development and tests. Production adapters can deny by actor, scope, tool name, risk
level, dealership, or tenant.

## Confirmation

High-impact writes require explicit `confirmed=true` before execution:

- `book_service_appointment`
- `reschedule_service_appointment`
- `cancel_service_appointment`
- `create_sales_lead`

When confirmation is missing, the executor returns `REQUIRES_CONFIRMATION` and does not mutate state.
Human handoff is classified as `ESCALATION` and does not require confirmation so safety escalation is
not blocked.

## Idempotency

Write tools accept an `idempotency_key`. The executor stores the first successful response in
`tool_idempotency_records`. A later call with the same key and identical validated payload replays the
stored response without repeating the mutation. A later call with the same key but different payload
returns `IDEMPOTENCY_CONFLICT`.

Booking tests verify that duplicate requests do not create duplicate appointments or double-book slot
capacity.

## Audit Logging

Every registered tool call is recorded in `tool_executions` with:

- request ID
- tool name
- conversation ID when available
- request payload
- structured response payload
- execution status
- confirmation requirement
- idempotency key when supplied
- timestamp

The executor also emits structured logs for success and failure.

## Transactional Integrity

Write execution and audit/idempotency persistence are committed together on success. Execution failures
roll back mutations, then record a failed audit response. Slot capacity is incremented on booking,
moved on reschedule, and released on cancellation through domain services.

## Current Limitations

- Tools are callable from tests, code, and the Phase 6 agent orchestration endpoint.
- Authorization is an interface with a permissive local default.
- The current LLM planner is intentionally minimal and deterministic in local mode.
- Migrations are still not implemented; table creation is metadata-driven in local/test flows.
