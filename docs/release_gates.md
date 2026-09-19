# AI Regression And Release Gates

Phase 10 adds a deterministic release gate for agent quality. The gate reads the latest evaluation
report, computes release metrics, compares them with version-controlled thresholds, and exits
non-zero when a change regresses below the accepted quality bar.

## Threshold Configuration

Thresholds are stored in:

```text
evaluation/quality_thresholds.json
```

The default gate configuration is:

- `task_success >= 0.90`
- `tool_selection_accuracy >= 0.95`
- `transaction_consistency >= 1.00`
- `pii_safety_pass_rate >= 1.00`
- `required_escalation_recall >= 0.95`
- `rag_retrieval_hit_rate >= 0.90`
- `hallucinated_transaction_rate <= 0.00`

These values are intentionally committed instead of embedded silently in code. Any threshold change
should be reviewed like production policy.

## Metric Definitions

- `task_success`: pass rate for the `task_success` scorer across all scenarios.
- `tool_selection_accuracy`: pass rate for expected tool calls in tool-selection scenarios.
- `transaction_consistency`: pass rate for applicable transaction consistency checks.
- `pii_safety_pass_rate`: scenario pass rate for PII/safety cases.
- `required_escalation_recall`: pass rate for applicable required-escalation checks.
- `rag_retrieval_hit_rate`: retrieval-hit scorer pass rate for RAG scenarios.
- `hallucinated_transaction_rate`: failure rate for applicable hallucinated-transaction checks.

## Commands

Run deterministic evaluations:

```bash
python -m evaluation.run
```

Run the release gate:

```bash
python -m evaluation.gate
```

or:

```bash
make evaluate
make gate
```

Exit code `0` means the release is accepted. Any non-zero exit code means the gate failed and the
deployment should stop until the regression is understood.

## Outputs

The evaluation runner writes:

- `evaluation/results/latest.json`
- `evaluation/results/latest.csv`
- `evaluation/results/latest.md`

The gate writes:

- `evaluation/results/quality_gate.json`
- `evaluation/results/quality_gate.md`

The Markdown report is designed for CI artifact upload and release review.

## CI Usage

The GitHub Actions workflow runs:

1. `ruff check .`
2. `mypy`
3. `pytest`
4. `python -m evaluation.run`
5. `python -m evaluation.gate`

CI fails if the gate exits non-zero. The workflow uploads `evaluation/results/` as the
`dealerai-quality-report` artifact whether the gate passes or fails.

## Team Workflow

Before deploying changes to prompts, provider adapters, tool schemas, RAG chunking, retrieval logic,
guardrails, or transactional tools:

1. Run unit tests and static checks.
2. Run deterministic agent evaluations.
3. Run the release gate.
4. Review failed metrics and individual failed scenarios in `latest.md`.
5. Review threshold changes separately from implementation changes.
6. Deploy only when the gate passes or when an explicitly approved exception is documented.

Future production model providers can attach token and cost metadata to the evaluation report without
changing the gate contract.
