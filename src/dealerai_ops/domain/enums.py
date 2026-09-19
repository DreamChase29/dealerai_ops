"""Domain enumerations for dealership operations."""

from enum import StrEnum


class AppointmentStatus(StrEnum):
    """Lifecycle states for service appointments."""

    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELED = "canceled"
    RESCHEDULED = "rescheduled"


class AppointmentChannel(StrEnum):
    """How a customer booked or requested service."""

    WEB = "web"
    PHONE = "phone"
    SMS = "sms"
    WALK_IN = "walk_in"
    SERVICE_ADVISOR = "service_advisor"


class AppointmentType(StrEnum):
    """Service appointment categories."""

    MAINTENANCE = "maintenance"
    REPAIR = "repair"
    DIAGNOSTIC = "diagnostic"
    RECALL = "recall"
    TIRE = "tire"


class InventoryStatus(StrEnum):
    """Inventory availability states."""

    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    IN_TRANSIT = "in_transit"


class LeadStatus(StrEnum):
    """Sales lead lifecycle states."""

    NEW = "new"
    CONTACTED = "contacted"
    APPOINTMENT_SET = "appointment_set"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class ConversationStatus(StrEnum):
    """Conversation states."""

    OPEN = "open"
    WAITING_ON_CUSTOMER = "waiting_on_customer"
    ESCALATED = "escalated"
    CLOSED = "closed"


class ToolExecutionStatus(StrEnum):
    """Typed tool execution outcomes."""

    REQUESTED = "requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REQUIRES_CONFIRMATION = "requires_confirmation"


class EscalationStatus(StrEnum):
    """Human escalation lifecycle states."""

    OPEN = "open"
    ASSIGNED = "assigned"
    RESOLVED = "resolved"
    CANCELED = "canceled"


class EscalationReason(StrEnum):
    """Structured reasons for human escalation."""

    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    TOOL_FAILURE = "TOOL_FAILURE"
    CUSTOMER_REQUEST = "CUSTOMER_REQUEST"
    POLICY_RESTRICTION = "POLICY_RESTRICTION"
    IDENTITY_AMBIGUITY = "IDENTITY_AMBIGUITY"
    REPEATED_FAILURE = "REPEATED_FAILURE"
    SENSITIVE_REQUEST = "SENSITIVE_REQUEST"
    SAFETY_CONCERN = "SAFETY_CONCERN"
