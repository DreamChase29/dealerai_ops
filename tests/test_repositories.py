from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from dealerai_ops.db.models import Customer
from dealerai_ops.domain.repositories import CustomerRepository
from dealerai_ops.domain.services import DealershipDomainService
from dealerai_ops.domain.synthetic import (
    SyntheticDatasetCounts,
    generate_synthetic_dataset,
    seed_session,
)


def test_customer_repository_crud_behavior(session: Session, sample_customer: Customer) -> None:
    repository = CustomerRepository(session)

    repository.add(sample_customer)
    session.commit()

    found = repository.get(sample_customer.id)
    assert found is not None
    assert found.synthetic_name == "Alex Test 0001"

    found.loyalty_tier = "gold"
    session.commit()

    updated = repository.get(sample_customer.id)
    assert updated is not None
    assert updated.loyalty_tier == "gold"

    assert repository.delete(sample_customer.id) is True
    session.commit()
    assert repository.get(sample_customer.id) is None


def test_domain_service_read_operations(session: Session) -> None:
    dataset = generate_synthetic_dataset(
        counts=SyntheticDatasetCounts(
            customers=20,
            owned_vehicles=25,
            inventory_vehicles=12,
            historical_appointments=60,
            future_service_days=5,
            sales_leads=10,
            conversations=12,
            tool_executions=15,
            escalations=3,
        ),
    )
    seed_session(session, dataset)
    service = DealershipDomainService(session)
    customer = dataset.customers[0]

    assert service.identify_customer(customer.id) is not None
    assert service.retrieve_customer_vehicles(customer.id)
    assert service.retrieve_customer_appointments(customer.id)
    assert service.recommend_service_slots(limit=3)
    assert len(service.search_inventory(limit=5)) <= 5


def test_customer_repository_lookup_by_email_hash(session: Session) -> None:
    customer = Customer(
        id="cus_repo_email",
        synthetic_name="Taylor Repo 0002",
        email_hash="repo-email-hash-0002",
        phone_last4="0202",
        preferred_contact_method="sms",
        acquisition_channel="service_referral",
        loyalty_tier="silver",
        distance_miles=Decimal("8.50"),
        credit_band=4,
        marketing_opt_in=False,
        prior_no_show_count=0,
        total_completed_appointments=0,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        last_activity_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    repository = CustomerRepository(session)

    repository.add(customer)
    session.commit()

    assert repository.get_by_email_hash("repo-email-hash-0002") is not None
    assert repository.get_by_email_hash("missing") is None
