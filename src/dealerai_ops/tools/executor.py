"""Validated, audited, and idempotent tool executor."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from dealerai_ops.db.models import ToolExecution, ToolIdempotencyRecord
from dealerai_ops.domain.enums import ToolExecutionStatus
from dealerai_ops.domain.repositories import (
    ToolExecutionRepository,
    ToolIdempotencyRepository,
)
from dealerai_ops.domain.services import DealershipDomainService
from dealerai_ops.observability import start_span
from dealerai_ops.tools.operations import (
    NoShowPredictionProvider,
    ToolDefinition,
    ToolRuntime,
    build_tool_registry,
)
from dealerai_ops.tools.types import (
    AllowAllAuthorizer,
    ToolAuthorizer,
    ToolCallResult,
    ToolContext,
    ToolError,
    ToolExecutionOutcome,
)

logger = structlog.get_logger(__name__)


class ToolExecutor:
    """Execute registered tools with validation, authorization, transactions, and audit."""

    def __init__(
        self,
        session: Session,
        authorizer: ToolAuthorizer | None = None,
        no_show_service: NoShowPredictionProvider | None = None,
        registry: dict[str, ToolDefinition] | None = None,
    ) -> None:
        self.session = session
        self.authorizer = authorizer or AllowAllAuthorizer()
        self.no_show_service = no_show_service
        self.registry = registry or build_tool_registry()

    def metadata(self) -> list[dict[str, Any]]:
        """Return metadata for all registered tools."""
        return [tool.metadata.model_dump(mode="json") for tool in self.registry.values()]

    def execute(
        self,
        tool_name: str,
        payload: dict[str, Any],
        context: ToolContext,
    ) -> ToolCallResult:
        """Validate and execute a tool call with telemetry."""
        tool = self.registry.get(tool_name)
        attributes: dict[str, Any] = {
            "tool_name": tool_name,
            "actor_id": context.actor_id,
            "payload_keys": sorted(payload),
        }
        if tool is not None:
            attributes.update(
                {
                    "risk_level": tool.risk_level.value,
                    "requires_confirmation": tool.requires_confirmation,
                }
            )
        with start_span(
            "tool_call",
            attributes=attributes,
            correlation_id=context.request_id,
            request_id=context.request_id,
            conversation_id=context.conversation_id,
        ) as span:
            result = self._execute_inner(tool_name, payload, context)
            span.set_attributes(
                {
                    "outcome": result.outcome.value,
                    "idempotent_replay": result.idempotent_replay,
                    "error_code": result.error.code if result.error is not None else None,
                }
            )
            if result.error is not None:
                span.mark_error(result.error.message, result.error.code)
            return result

    def _execute_inner(
        self,
        tool_name: str,
        payload: dict[str, Any],
        context: ToolContext,
    ) -> ToolCallResult:
        """Validate and execute a tool call deterministically."""
        tool = self.registry.get(tool_name)
        if tool is None:
            return self._record_failure(
                tool_name=tool_name,
                payload=payload,
                context=context,
                code="UNKNOWN_TOOL",
                message=f"Tool is not registered: {tool_name}",
            )

        try:
            parsed = tool.input_model.model_validate(payload)
        except ValidationError as exc:
            return self._record_failure(
                tool_name=tool.name,
                payload=payload,
                context=context,
                code="VALIDATION_ERROR",
                message="Tool input validation failed.",
                details={"errors": exc.errors()},
            )

        parsed_payload = parsed.model_dump(mode="json")
        decision = self.authorizer.authorize(context, tool.metadata, parsed_payload)
        if not decision.allowed:
            return self._record_failure(
                tool_name=tool.name,
                payload=parsed_payload,
                context=context,
                code="UNAUTHORIZED",
                message=decision.reason or "Tool call is not authorized.",
                outcome=ToolExecutionOutcome.UNAUTHORIZED,
            )

        if tool.requires_confirmation and not bool(getattr(parsed, "confirmed", False)):
            result = ToolCallResult(
                request_id=context.request_id,
                tool_name=tool.name,
                outcome=ToolExecutionOutcome.REQUIRES_CONFIRMATION,
                error=ToolError(
                    code="CONFIRMATION_REQUIRED",
                    message="This tool requires explicit confirmation before execution.",
                ),
            )
            self._audit(tool, parsed_payload, context, result)
            self.session.commit()
            return result

        idempotency_key = _extract_idempotency_key(parsed)
        request_hash = _request_hash(tool.name, parsed_payload)
        try:
            replay = self._replay_idempotent_result(tool, idempotency_key, request_hash, context)
            if replay is not None:
                return replay

            runtime = ToolRuntime(
                domain=DealershipDomainService(self.session),
                no_show_service=self.no_show_service,
            )
            output = tool.handler(runtime, parsed)
            data = output.model_dump(mode="json")
            result = ToolCallResult(
                request_id=context.request_id,
                tool_name=tool.name,
                outcome=ToolExecutionOutcome.SUCCEEDED,
                data=data,
            )
            if idempotency_key is not None:
                self._store_idempotency(tool, idempotency_key, request_hash, data)
            self._audit(tool, parsed_payload, context, result, idempotency_key)
            self.session.commit()
            logger.info(
                "tool_execution_succeeded",
                request_id=context.request_id,
                tool_name=tool.name,
            )
            return result
        except (SQLAlchemyError, ValueError) as exc:
            self.session.rollback()
            return self._record_failure(
                tool_name=tool.name,
                payload=parsed_payload,
                context=context,
                code="EXECUTION_ERROR",
                message=str(exc),
                idempotency_key=idempotency_key,
            )

    def _replay_idempotent_result(
        self,
        tool: ToolDefinition,
        idempotency_key: str | None,
        request_hash: str,
        context: ToolContext,
    ) -> ToolCallResult | None:
        if idempotency_key is None:
            return None
        existing = ToolIdempotencyRepository(self.session).get_by_key(idempotency_key)
        if existing is None:
            return None
        if existing.tool_name != tool.name or existing.request_hash != request_hash:
            result = ToolCallResult(
                request_id=context.request_id,
                tool_name=tool.name,
                outcome=ToolExecutionOutcome.FAILED,
                error=ToolError(
                    code="IDEMPOTENCY_CONFLICT",
                    message="Idempotency key was already used for a different request.",
                ),
            )
            self._audit(
                tool,
                {"idempotency_key": idempotency_key},
                context,
                result,
                idempotency_key,
            )
            self.session.commit()
            return result

        result = ToolCallResult(
            request_id=context.request_id,
            tool_name=tool.name,
            outcome=ToolExecutionOutcome.SUCCEEDED,
            data=existing.response_payload,
            idempotent_replay=True,
        )
        self._audit(
            tool,
            {"idempotency_key": idempotency_key},
            context,
            result,
            idempotency_key,
        )
        self.session.commit()
        return result

    def _store_idempotency(
        self,
        tool: ToolDefinition,
        idempotency_key: str,
        request_hash: str,
        data: dict[str, Any],
    ) -> None:
        repo = ToolIdempotencyRepository(self.session)
        repo.add(
            ToolIdempotencyRecord(
                id=_stable_id("idem", idempotency_key),
                idempotency_key=idempotency_key,
                tool_name=tool.name,
                request_hash=request_hash,
                response_payload=data,
                created_at=datetime.now(UTC),
            )
        )

    def _record_failure(
        self,
        tool_name: str,
        payload: dict[str, Any],
        context: ToolContext,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        outcome: ToolExecutionOutcome = ToolExecutionOutcome.FAILED,
        idempotency_key: str | None = None,
    ) -> ToolCallResult:
        result = ToolCallResult(
            request_id=context.request_id,
            tool_name=tool_name,
            outcome=outcome,
            error=ToolError(code=code, message=message, details=details or {}),
        )
        tool = self.registry.get(tool_name)
        if tool is not None:
            try:
                self._audit(tool, payload, context, result, idempotency_key)
                self.session.commit()
            except SQLAlchemyError as exc:
                self.session.rollback()
                logger.warning(
                    "tool_failure_audit_failed",
                    request_id=context.request_id,
                    tool_name=tool_name,
                    code=code,
                    audit_error=str(exc),
                )
        logger.warning(
            "tool_execution_failed",
            request_id=context.request_id,
            tool_name=tool_name,
            code=code,
            message=message,
        )
        return result

    def _audit(
        self,
        tool: ToolDefinition,
        payload: dict[str, Any],
        context: ToolContext,
        result: ToolCallResult,
        idempotency_key: str | None = None,
    ) -> None:
        status = {
            ToolExecutionOutcome.SUCCEEDED: ToolExecutionStatus.SUCCEEDED,
            ToolExecutionOutcome.FAILED: ToolExecutionStatus.FAILED,
            ToolExecutionOutcome.REQUIRES_CONFIRMATION: ToolExecutionStatus.REQUIRES_CONFIRMATION,
            ToolExecutionOutcome.UNAUTHORIZED: ToolExecutionStatus.FAILED,
        }[result.outcome]
        ToolExecutionRepository(self.session).add(
            ToolExecution(
                id=_stable_id("tool", f"{context.request_id}:{tool.name}"),
                conversation_id=context.conversation_id,
                appointment_id=_appointment_id_from_result(result),
                request_id=context.request_id,
                tool_name=tool.name,
                status=status,
                request_payload=payload,
                response_payload=result.model_dump(mode="json"),
                requires_confirmation=tool.requires_confirmation,
                idempotency_key=idempotency_key,
                created_at=datetime.now(UTC),
            )
        )


def _extract_idempotency_key(payload: BaseModel) -> str | None:
    value = getattr(payload, "idempotency_key", None)
    return value if isinstance(value, str) and value else None


def _request_hash(tool_name: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"tool_name": tool_name, "payload": payload},
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_id(prefix: str, key: str) -> str:
    return f"{prefix}_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]}"


def _appointment_id_from_result(result: ToolCallResult) -> str | None:
    if result.data is None:
        return None
    appointment = result.data.get("appointment")
    if isinstance(appointment, dict):
        appointment_id = appointment.get("id")
        if isinstance(appointment_id, str):
            return appointment_id
    return None
