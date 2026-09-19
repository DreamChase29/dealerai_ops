"""Demo escalation read endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from dealerai_ops.db.session import get_session
from dealerai_ops.escalations.schemas import EscalationListResponse, EscalationRecord
from dealerai_ops.escalations.service import EscalationService

router = APIRouter(prefix="/escalations", tags=["escalations"])

SessionDependency = Annotated[Session, Depends(get_session)]


@router.get("", response_model=EscalationListResponse)
def list_escalations(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EscalationListResponse:
    """List human escalation records for the demo app."""
    service = EscalationService(session)
    return EscalationListResponse(
        escalations=service.list_escalations(limit=limit, offset=offset),
        limit=limit,
        offset=offset,
    )


@router.get("/{escalation_id}", response_model=EscalationRecord)
def get_escalation(
    escalation_id: str,
    session: SessionDependency,
) -> EscalationRecord:
    """Return one escalation record by ID."""
    service = EscalationService(session)
    record = service.get_escalation(escalation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Escalation not found.")
    return record
