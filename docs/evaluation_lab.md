# Agent Evaluation Laboratory

Phase 9 adds a deterministic evaluation lab for agent, tool, RAG, safety, and transactional
regression testing. The lab is intentionally provider-independent: it drives the existing
orchestrator with scripted structured model responses so the tests exercise system behavior without
paid API access or nondeterministic model sampling.

## Scope

The scenario generator creates 121 deterministic scenarios across:

- normal customer scenarios
- multi-turn scenarios
- tool-selection scenarios
- tool-argument scenarios
- RAG scenarios
- transaction scenarios
- tool-failure scenarios
- human-escalation scenarios
- PII/safety scenarios
- prompt-injection scenarios
- historical regression scenarios

Each scenario defines user turns, scripted model responses, and expected behavior. Transactional
scenarios run against a fresh deterministic in-memory SQLite database so scenario order cannot affect
appointment slot capacity, idempotency records, or escalation state.

## Scorers

The evaluator emits one score result per scorer:

- `task_success`
- `expected_tool_called`
- `unexpected_tool_called`
- `tool_argument_accuracy`
- `transaction_state_consistency`
- `retrieval_hit`
- `citation_presence`
- `citation_correctness`
- `PII_leakage`
- `required_escalation`
- `unnecessary_escalation`
- `policy_violation`
- `hallucinated_transaction`

Tool argument accuracy is scored from the deterministic model-request trace, not from tool response
payloads. This preserves the production boundary where tools audit their validated input but do not
need to echo raw model arguments in user-facing results.

## Captured Metadata

Each scenario captures:

- latency in milliseconds
- number of model calls
- number of tool calls
- retrieval count
- token metadata when a provider supplies it
- estimated cost when input and output token pricing are configured
- requested tool argument traces for scorer diagnostics

The default local scripted provider does not produce token metadata, so estimated cost defaults to
zero unless token counts and pricing are supplied by a future provider adapter.

## Reports

Run the lab with:

```bash
python -m evaluation.run
```

or:

```bash
make evaluate
```

The runner writes:

- `evaluation/results/latest.json`
- `evaluation/results/latest.csv`
- `evaluation/results/latest.md`

The Markdown report includes aggregate metrics, category pass rates, scorer pass rates, every failed
case with failed scorer details, and an individual-case table. Failed scenarios are intentionally not
hidden behind an aggregate pass rate.

## Limitations

- The current lab uses scripted local model responses, so it validates orchestration, policies,
  tools, retrieval, and scorer behavior rather than live-model prompt quality.
- Cost estimation is wired for provider metadata but remains zero in the deterministic local mode.
- Citation correctness is deterministic only for expected document IDs; it does not yet grade
  sentence-level attribution.
- Historical regression cases are hand-authored. Future phases should add fixtures from real defects
  discovered during development.

## Future Regression Gates

Phase 10 implements CI-ready regression gates:

- version-controlled thresholds in `evaluation/quality_thresholds.json`
- `python -m evaluation.gate`
- Markdown and JSON quality reports under `evaluation/results`
- non-zero exit code for release-blocking regressions

See [release_gates.md](release_gates.md) for threshold definitions and deployment workflow guidance.
