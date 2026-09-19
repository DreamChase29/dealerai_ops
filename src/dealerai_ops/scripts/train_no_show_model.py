"""Train and serialize the deterministic no-show prediction model."""

import argparse

import structlog

from dealerai_ops.core.config import get_settings
from dealerai_ops.core.logging import configure_logging
from dealerai_ops.ml.training import train_and_serialize_default_model

logger = structlog.get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the training script argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", default=None, help="Override DEALERAI_NO_SHOW_MODEL_DIR.")
    parser.add_argument("--model-version", default=None, help="Override model version metadata.")
    return parser


def main() -> None:
    """Train and persist the no-show prediction model."""
    settings = get_settings()
    configure_logging(settings.log_level)
    args = build_parser().parse_args()
    result = train_and_serialize_default_model(
        model_dir=args.model_dir or settings.no_show_model_dir,
        model_version=args.model_version or settings.no_show_model_version,
    )
    logger.info(
        "no_show_training_complete",
        model_dir=str(result.model_dir),
        metadata=result.artifact.metadata,
        test_metrics=result.artifact.metrics["test"],
    )


if __name__ == "__main__":
    main()
