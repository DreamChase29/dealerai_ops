"""Seed a database with deterministic synthetic dealership data."""

import argparse

import structlog

from dealerai_ops.core.config import get_settings
from dealerai_ops.core.logging import configure_logging
from dealerai_ops.db.base import Base
from dealerai_ops.db.models import Customer
from dealerai_ops.db.session import create_db_engine, create_session_factory
from dealerai_ops.domain.synthetic import (
    DEFAULT_SYNTHETIC_SEED,
    SyntheticDatasetCounts,
    generate_synthetic_dataset,
    seed_session,
)

logger = structlog.get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the seed script argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None, help="Override DEALERAI_DATABASE_URL.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SYNTHETIC_SEED)
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables first.")
    return parser


def main() -> None:
    """Run the synthetic database seeding workflow."""
    settings = get_settings()
    configure_logging(settings.log_level)
    args = build_parser().parse_args()
    database_url = args.database_url or settings.database_url

    engine = create_db_engine(database_url)
    if args.reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    session_factory = create_session_factory(engine)
    with session_factory() as session:
        existing_customer = session.get(Customer, "cus_00000001")
        if existing_customer is not None and not args.reset:
            logger.info("synthetic_seed_skipped", reason="existing_seed_data")
            return

        dataset = generate_synthetic_dataset(
            counts=SyntheticDatasetCounts(),
            seed=args.seed,
        )
        summary = seed_session(session, dataset)
        logger.info("synthetic_seed_complete", **summary)


if __name__ == "__main__":
    main()
