from __future__ import annotations

from typing import Any

SENSITIVE_KEYS = {
    "ip",
    "ip_address",
    "client_ip",
    "email",
    "email_address",
    "phone",
    "phone_number",
    "mobile",
    "name",
    "full_name",
    "address",
    "location",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "credential",
}


def redact_sensitive_fields(value: Any, key: str = "") -> Any:
    """Redact explicit secret/PII fields at the AI API boundary without touching business IDs."""
    normalized = key.lower()
    if normalized in SENSITIVE_KEYS and value not in (None, ""):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): redact_sensitive_fields(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_fields(item, key) for item in value]
    return value
