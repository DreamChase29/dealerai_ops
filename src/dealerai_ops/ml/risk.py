"""Operational risk tiering and threshold analysis."""

from dataclasses import dataclass

import numpy as np
from sklearn.metrics import f1_score, precision_score, recall_score

from dealerai_ops.ml.schemas import RiskTier


@dataclass(frozen=True)
class RiskBand:
    """Probability interval mapped to an operational tier."""

    tier: RiskTier
    min_probability: float
    max_probability: float


RISK_BANDS: tuple[RiskBand, ...] = (
    RiskBand(RiskTier.LOW, 0.0, 0.10),
    RiskBand(RiskTier.MEDIUM, 0.10, 0.20),
    RiskBand(RiskTier.HIGH, 0.20, 0.35),
    RiskBand(RiskTier.VERY_HIGH, 0.35, 1.01),
)


def risk_tier_for_probability(probability: float) -> RiskTier:
    """Map a probability to an operational risk tier."""
    for band in RISK_BANDS:
        if band.min_probability <= probability < band.max_probability:
            return band.tier
    return RiskTier.VERY_HIGH


def threshold_analysis(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    thresholds: tuple[float, ...] = (0.10, 0.15, 0.20, 0.25, 0.35, 0.50),
) -> list[dict[str, float]]:
    """Calculate operational tradeoff metrics across decision thresholds."""
    rows: list[dict[str, float]] = []
    for threshold in thresholds:
        predictions = probabilities >= threshold
        rows.append(
            {
                "threshold": threshold,
                "flag_rate": float(np.mean(predictions)),
                "precision": float(precision_score(y_true, predictions, zero_division=0)),
                "recall": float(recall_score(y_true, predictions, zero_division=0)),
                "f1": float(f1_score(y_true, predictions, zero_division=0)),
            },
        )
    return rows
