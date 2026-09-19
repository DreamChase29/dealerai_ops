# Synthetic Customer Privacy Policy

Fictional/synthetic demonstration material for DealerAI Ops. This content is not legal advice and does
not represent a real privacy policy.

## Synthetic Data Only

DealerAI Ops uses synthetic demonstration records. Real customer personally identifiable information
should not be required for local development, tests, demos, or model evaluation.

## PII Handling

If a real deployment is considered, tools should minimize exposure of personal data. Customer lookup
responses should avoid unnecessary sensitive fields. Logs should use request IDs and stable synthetic
identifiers instead of raw phone numbers, email addresses, or free-form personal details.

## Consent And Contact Preferences

Marketing contact must respect the synthetic opt-in flag. Operational service messages may be treated
differently from promotional messages in the fictional policy, but production rules require legal
review.

## Data Retention

Synthetic demo logs may be retained for testing and debugging. Real deployments should define retention
periods for conversations, tool execution audit rows, lead records, and model inference logs.

## Model Privacy

No-show prediction should not use protected-class features or direct identifiers. Monitoring should
include schema validation, feature drift, and fairness review before any real-world use.
