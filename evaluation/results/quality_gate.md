# DealerAI Ops Quality Gate Report

Generated at: `2026-08-11T17:12:02.391754+00:00`
Threshold version: `phase10-defaults-2026-08-11`
Evaluation results: `evaluation\results\latest.json`
Release decision: **ACCEPTED**

| Metric | Value | Threshold | Result | Definition |
| --- | ---: | ---: | --- | --- |
| `task_success` | 1.0000 (121/121) | >= 0.9000 | pass | Pass rate for the task_success scorer across all scenarios. |
| `tool_selection_accuracy` | 1.0000 (11/11) | >= 0.9500 | pass | Pass rate for expected tool calls in tool-selection scenarios. |
| `transaction_consistency` | 1.0000 (28/28) | >= 1.0000 | pass | Pass rate for applicable transaction_state_consistency scorer results. |
| `pii_safety_pass_rate` | 1.0000 (11/11) | >= 1.0000 | pass | Scenario pass rate for PII/safety scenarios. |
| `required_escalation_recall` | 1.0000 (40/40) | >= 0.9500 | pass | Pass rate for applicable required_escalation scorer results. |
| `rag_retrieval_hit_rate` | 1.0000 (11/11) | >= 0.9000 | pass | Pass rate for RAG retrieval_hit scorer results. |
| `hallucinated_transaction_rate` | 0.0000 (0/121) | <= 0.0000 | pass | Failure rate for applicable hallucinated_transaction scorer results. |
