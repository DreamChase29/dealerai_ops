# No-Show Prediction System

## Problem Definition

The Phase 3 ML component estimates the probability that a synthetic service appointment will become
a no-show. The prediction is intended for operational planning, such as reminder intensity, service
advisor follow-up, and slot overbooking analysis. It is not a customer eligibility, pricing, financing,
or punitive decision system.

## Training Data

Training data is derived from the deterministic synthetic dealership dataset. The supervised target is:

```text
1 = appointment status is NO_SHOW
0 = appointment status is COMPLETED
```

Canceled, rescheduled, and still-confirmed historical rows are excluded from model training because
they represent different operational outcomes.

## Features

The model uses only booking-time or pre-booking information:

- appointment type
- booking channel
- lead time in days
- estimated duration
- first service visit flag
- prior no-show count at booking
- prior completed appointment count at booking
- reminder count
- scheduled day of week
- scheduled hour
- days since synthetic customer creation at booking
- vehicle age at booking
- customer distance to dealership
- loyalty tier
- acquisition channel
- preferred contact method
- marketing opt-in

The feature set intentionally excludes protected-class fields and direct identifiers.

## Leakage Controls

Feature extraction explicitly blocks known leakage fields:

- appointment status
- completed, canceled, and confirmed timestamps
- service history details created after completion
- appointment/customer/vehicle IDs
- synthetic name, email hash, and phone last four
- current mileage
- aggregate customer totals computed after the full dataset is generated

Historical prior counts are recomputed in booking-time order before training so they reflect information
available at the time of the appointment request.

## Model Training

Training uses sklearn-native pipelines so preprocessing and inference transformations cannot diverge.
Both candidate models include the same `ColumnTransformer` preprocessing layer:

- numeric median imputation and standard scaling
- categorical most-frequent imputation and one-hot encoding

Candidate models:

- logistic regression baseline
- histogram gradient boosting classifier

Both candidates are probability-calibrated with `CalibratedClassifierCV`. Model selection is based on
validation Brier score, tie-broken by average precision. This avoids selecting a model merely because
it has higher accuracy on an imbalanced problem.

## Metrics

Training records:

- ROC-AUC
- average precision / PR-AUC
- precision at threshold `0.20`
- recall at threshold `0.20`
- F1 at threshold `0.20`
- Brier score
- confusion matrix at threshold `0.20`
- calibration curve diagnostics
- threshold analysis

## Threshold Rationale

The default operating threshold for binary metrics is `0.20`, chosen as a service operations tradeoff:
it flags more risky appointments for reminder or advisor follow-up while avoiding the much broader
flag volume produced by lower thresholds. Threshold analysis is serialized so operations teams can
choose a different intervention threshold depending on staffing, slot scarcity, and acceptable false
positive volume.

Operational risk bands:

| Tier | Probability |
| --- | --- |
| LOW | `[0.00, 0.10)` |
| MEDIUM | `[0.10, 0.20)` |
| HIGH | `[0.20, 0.35)` |
| VERY_HIGH | `[0.35, 1.00]` |

## Serialized Artifacts

The training command writes:

- `model.joblib`
- `feature_schema.json`
- `metadata.json`
- `metrics.json`

Metadata includes model version, selected model, training timestamp, dataset version, dataset
fingerprint, split sizes, random seed, positive rate, and risk bands.

## API

```text
POST /ml/no-show/predict
```

The response includes:

- calibrated no-show probability
- operational risk tier
- model version

## Limitations

- Data is synthetic and not a substitute for dealership-specific validation.
- Synthetic relationships may underrepresent seasonal campaigns, local events, weather, and advisor
  behavior.
- Credit, demographic, and protected-class fields are not used; distance and channel may still require
  fairness review before real-world use.
- The current model predicts only no-show versus completed appointments.

## Drift Risks

Monitor for:

- no-show base-rate changes
- booking channel mix changes
- appointment type mix changes
- reminder policy changes
- calibration drift
- new vehicle/service categories
- changed cancellation or rescheduling workflows

## Monitoring Plan

Production monitoring should track:

- prediction volume
- latency
- input schema validation failures
- missing or unknown categorical values
- probability distribution by risk tier
- observed no-show rate by risk tier
- Brier score on matured appointments
- precision and recall at operational thresholds
- calibration by decile

## Retraining Triggers

Retrain when:

- monthly Brier score degrades materially from validation baseline
- observed no-show rate shifts by more than 20% relative
- high-risk tier precision or recall degrades materially
- more than 5% of categorical inputs are unseen values
- service scheduling policy changes
- reminder workflow changes
- a new dealership/location is added
