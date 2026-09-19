from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from dealerai_ops.db.base import Base
from dealerai_ops.db.models import Customer
from dealerai_ops.db.session import create_db_engine, create_session_factory


@pytest.fixture
def engine() -> Generator[Engine, None, None]:
    db_engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(db_engine)
    try:
        yield db_engine
    finally:
        Base.metadata.drop_all(db_engine)
        db_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Generator[Session, None, None]:
    session_factory = create_session_factory(engine)
    with session_factory() as db_session:
        yield db_session


@pytest.fixture
def sample_customer() -> Customer:
    return Customer(
        id="cus_test_00000001",
        synthetic_name="Alex Test 0001",
        email_hash="test-email-hash-0001",
        phone_last4="0101",
        preferred_contact_method="email",
        acquisition_channel="organic_search",
        loyalty_tier="standard",
        distance_miles=Decimal("10.25"),
        credit_band=3,
        marketing_opt_in=True,
        prior_no_show_count=0,
        total_completed_appointments=0,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        last_activity_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
