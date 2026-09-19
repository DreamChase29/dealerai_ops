# Portfolio Demo UI

Phase 12 adds a Streamlit portfolio interface for demonstrating DealerAI Ops with synthetic data and
deterministic local providers.

## Run

```bash
python -m pip install -e ".[dev]"
make demo-ui
```

The app uses a smaller deterministic in-memory dataset for responsiveness. The production seed script
still generates the larger Phase 2 dataset.

## Pages

- AI Service Assistant: conversation, retrieved sources, typed tool activity, confirmation requests,
  and final outcome.
- Customer 360: redacted synthetic customer profile, operating features, and owned vehicles.
- Vehicle Inventory: synthetic inventory table and availability mix.
- Service Appointments: appointment lifecycle and future service-slot capacity.
- No-Show Risk: deterministic operational risk estimates and risk-band distribution.
- Agent Trace: redacted operational spans for model calls, retrieval, tool calls, guardrail decisions,
  escalation, and latency.
- RAG Sources: retrieval results and synthetic knowledge corpus inventory.
- Evaluation Dashboard: task success, tool accuracy, RAG, safety, escalation, latency-oriented quality
  signals, and regression gate status.
- Human Escalations: synthetic escalation queue for demo operations.
- System Architecture: implemented layers and data flow.

## Safety Boundary

The UI does not expose hidden chain-of-thought. It shows operational trace metadata only:

- model call event
- retrieval event
- requested tool and tool result
- guardrail decision
- escalation event
- latency and redacted attributes

Transactional actions still flow through the typed tool executor. Booking requires explicit
confirmation, and the assistant page only reports success after the booking tool returns a successful
structured result.

## Limitations

- The UI is a portfolio demonstration, not an authenticated production console.
- The assistant scenarios are deterministic so the demo works without paid LLM APIs.
- The in-memory demo dataset resets when the Streamlit process restarts.
- The UI reads committed evaluation and release-gate artifacts; teams should regenerate those reports
  after changing prompts, tools, retrieval, guardrails, or models.
