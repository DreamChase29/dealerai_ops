"""PII and secret redaction helpers for structured logs."""

import re
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

REDACTION = "[REDACTED]"

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)")
SSN_PATTERN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
LONG_SECRET_PATTERN = re.compile(
    r"(?i)\b(?:password|passwd|secret|api[_-]?key|token|credential)s?\b\s*[:=]\s*[^\s,;]+"
)

SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "token",
    "credential",
    "credentials",
    "phone",
    "phone_number",
    "email",
}


def redact_text(value: str) -> str:
    """Redact obvious PII and secret-like values from a string."""
    redacted = EMAIL_PATTERN.sub(REDACTION, value)
    redacted = PHONE_PATTERN.sub(REDACTION, redacted)
    redacted = SSN_PATTERN.sub(REDACTION, redacted)
    return LONG_SECRET_PATTERN.sub(REDACTION, redacted)


def redact_value(value: Any) -> Any:
    """Recursively redact supported values for logging."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            key: REDACTION if str(key).lower() in SENSITIVE_KEYS else redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_value(item) for item in value]
    return value


def redact_structlog_event(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> Mapping[str, Any]:
    """Structlog processor that redacts PII and secret-like values."""
    return {key: redact_value(value) for key, value in event_dict.items()}
