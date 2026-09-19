"""Repository abstractions for dealership domain persistence."""

from collections.abc import Sequence
from typing import Generic, Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from dealerai_ops.db.models import (
    Conversation,
    Customer,
    Escalation,
    InventoryVehicle,
    SalesLead,
    ServiceAppointment,
    ServiceHistory,
    ServiceSlot,
    ToolExecution,
    ToolIdempotencyRecord,
    Vehicle,
)
from dealerai_ops.domain.enums import AppointmentStatus, InventoryStatus

ModelT = TypeVar("ModelT")


class Repository(Protocol[ModelT]):
    """Minimal CRUD contract used by domain services and future tools."""

    def add(self, entity: ModelT) -> ModelT:
        """Persist an entity."""

    def get(self, entity_id: str) -> ModelT | None:
        """Return an entity by ID."""

    def list(self, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """Return a page of entities."""

    def delete(self, entity_id: str) -> bool:
        """Delete an entity by ID if it exists."""


class SqlAlchemyRepository(Generic[ModelT]):
    """Reusable SQLAlchemy-backed repository implementation."""

    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def add(self, entity: ModelT) -> ModelT:
        """Persist an entity and flush pending SQL."""
        self.session.add(entity)
        self.session.flush()
        return entity

    def get(self, entity_id: str) -> ModelT | None:
        """Return an entity by primary key."""
        return self.session.get(self.model, entity_id)

    def list(self, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """Return a page of entities."""
        stmt = select(self.model).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def delete(self, entity_id: str) -> bool:
        """Delete an entity by ID if present."""
        entity = self.get(entity_id)
        if entity is None:
            return False
        self.session.delete(entity)
        self.session.flush()
        return True


class CustomerRepository(SqlAlchemyRepository[Customer]):
    """Repository for customers."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Customer)

    def get_by_email_hash(self, email_hash: str) -> Customer | None:
        """Return a customer by synthetic email hash."""
        return self.session.scalar(select(Customer).where(Customer.email_hash == email_hash))


class VehicleRepository(SqlAlchemyRepository[Vehicle]):
    """Repository for owned vehicles."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Vehicle)

    def list_for_customer(self, customer_id: str) -> list[Vehicle]:
        """Return vehicles owned by a customer."""
        stmt = select(Vehicle).where(Vehicle.customer_id == customer_id).order_by(Vehicle.id)
        return list(self.session.scalars(stmt).all())

    def get_for_customer(self, customer_id: str, vehicle_id: str) -> Vehicle | None:
        """Return a vehicle only when it belongs to the customer."""
        stmt = select(Vehicle).where(Vehicle.customer_id == customer_id, Vehicle.id == vehicle_id)
        return self.session.scalar(stmt)


class InventoryVehicleRepository(SqlAlchemyRepository[InventoryVehicle]):
    """Repository for dealership inventory."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, InventoryVehicle)

    def search_available(
        self,
        make: str | None = None,
        model: str | None = None,
        limit: int = 25,
    ) -> list[InventoryVehicle]:
        """Search available synthetic inventory by make and optional model."""
        stmt = select(InventoryVehicle).where(InventoryVehicle.status == InventoryStatus.AVAILABLE)
        if make is not None:
            stmt = stmt.where(InventoryVehicle.make == make)
        if model is not None:
            stmt = stmt.where(InventoryVehicle.model == model)
        stmt = stmt.order_by(InventoryVehicle.list_price, InventoryVehicle.id).limit(limit)
        return list(self.session.scalars(stmt).all())


class ServiceAppointmentRepository(SqlAlchemyRepository[ServiceAppointment]):
    """Repository for service appointments."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ServiceAppointment)

    def list_for_customer(self, customer_id: str, limit: int = 50) -> list[ServiceAppointment]:
        """Return recent appointments for a customer."""
        stmt = (
            select(ServiceAppointment)
            .where(ServiceAppointment.customer_id == customer_id)
            .order_by(ServiceAppointment.scheduled_start_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def count_completed_before_customer(self, customer_id: str) -> int:
        """Return completed appointment count for a customer."""
        stmt = select(ServiceAppointment).where(
            ServiceAppointment.customer_id == customer_id,
            ServiceAppointment.status == AppointmentStatus.COMPLETED,
        )
        return len(list(self.session.scalars(stmt).all()))

    def count_no_show_before_customer(self, customer_id: str) -> int:
        """Return no-show appointment count for a customer."""
        stmt = select(ServiceAppointment).where(
            ServiceAppointment.customer_id == customer_id,
            ServiceAppointment.status == AppointmentStatus.NO_SHOW,
        )
        return len(list(self.session.scalars(stmt).all()))


class ServiceHistoryRepository(SqlAlchemyRepository[ServiceHistory]):
    """Repository for completed service history."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ServiceHistory)

    def list_for_vehicle(self, vehicle_id: str, limit: int = 50) -> list[ServiceHistory]:
        """Return service records for a vehicle."""
        stmt = (
            select(ServiceHistory)
            .where(ServiceHistory.vehicle_id == vehicle_id)
            .order_by(ServiceHistory.service_date.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())


class ServiceSlotRepository(SqlAlchemyRepository[ServiceSlot]):
    """Repository for service capacity slots."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ServiceSlot)

    def list_available(
        self, bay_types: Sequence[str] | None = None, limit: int = 25
    ) -> list[ServiceSlot]:
        """Return future slots with remaining capacity."""
        stmt = select(ServiceSlot).where(ServiceSlot.booked_count < ServiceSlot.capacity)
        if bay_types:
            stmt = stmt.where(ServiceSlot.bay_type.in_(bay_types))
        stmt = stmt.order_by(ServiceSlot.starts_at, ServiceSlot.id).limit(limit)
        return list(self.session.scalars(stmt).all())

    def reserve_capacity(self, slot: ServiceSlot) -> None:
        """Increment booked capacity for a slot with availability validation."""
        if slot.booked_count >= slot.capacity:
            raise ValueError("Service slot has no remaining capacity.")
        slot.booked_count += 1
        self.session.flush()

    def release_capacity(self, slot: ServiceSlot) -> None:
        """Decrement booked capacity when an appointment leaves a slot."""
        if slot.booked_count > 0:
            slot.booked_count -= 1
            self.session.flush()


class SalesLeadRepository(SqlAlchemyRepository[SalesLead]):
    """Repository for sales leads."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, SalesLead)


class ConversationRepository(SqlAlchemyRepository[Conversation]):
    """Repository for conversation metadata."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Conversation)


class ToolExecutionRepository(SqlAlchemyRepository[ToolExecution]):
    """Repository for tool execution audit events."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ToolExecution)


class ToolIdempotencyRepository(SqlAlchemyRepository[ToolIdempotencyRecord]):
    """Repository for idempotent write response records."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ToolIdempotencyRecord)

    def get_by_key(self, idempotency_key: str) -> ToolIdempotencyRecord | None:
        """Return an idempotency record by key."""
        stmt = select(ToolIdempotencyRecord).where(
            ToolIdempotencyRecord.idempotency_key == idempotency_key
        )
        return self.session.scalar(stmt)


class EscalationRepository(SqlAlchemyRepository[Escalation]):
    """Repository for human escalations."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Escalation)
