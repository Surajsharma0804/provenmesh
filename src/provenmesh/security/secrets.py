"""Secrets management — safe loading and sanitization (PDF §10.3).

API keys are loaded from environment variables via .env (git-ignored),
never hardcoded. This module ensures secrets never leak into logs,
exceptions, or error messages.
"""

from __future__ import annotations

import os
import re
from typing import Any

from pydantic import SecretStr

from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

# Patterns that look like secrets
_SECRET_PATTERNS = re.compile(
    r"(api[_-]?key|token|password|secret|credential|auth|bearer)"
    r"\s*[=:]\s*\S+",
    re.IGNORECASE,
)


def get_secret(key: str, default: str = "") -> str:
    """Safely retrieve a secret from environment variables.

    Never log the actual value — only whether it was found.
    """
    value = os.environ.get(key, default)
    if value and value != default:
        logger.debug("secret_loaded", key=key, found=True)
    else:
        logger.warning("secret_missing", key=key, found=False)
    return value


def mask_secret(value: str, visible_chars: int = 4) -> str:
    """Mask a secret value for safe logging.

    Shows only the first `visible_chars` characters, replaces rest with asterisks.
    """
    if not value or len(value) <= visible_chars:
        return "****"
    return value[:visible_chars] + "*" * (len(value) - visible_chars)


def redact_secrets(text: str) -> str:
    """Remove potential secrets from text (for safe error logging)."""
    return _SECRET_PATTERNS.sub("[REDACTED]", text)


def safe_str(secret: SecretStr | str | None) -> str:
    """Extract the string value from a SecretStr or return empty string."""
    if secret is None:
        return ""
    if isinstance(secret, SecretStr):
        return secret.get_secret_value()
    return secret


def validate_required_secrets(keys: list[str]) -> dict[str, bool]:
    """Check that all required secrets are present. Returns status dict."""
    status: dict[str, bool] = {}
    for key in keys:
        value = os.environ.get(key, "")
        present = bool(value) and value not in ("", "your_key_here", "placeholder")
        status[key] = present
        if not present:
            logger.warning("required_secret_missing", key=key)
    return status


def sanitize_for_logging(data: dict[str, Any]) -> dict[str, Any]:
    """Deep-sanitize a dict, masking any values that look like secrets."""
    sanitized = {}
    secret_keys = {"key", "token", "password", "secret", "credential", "auth", "dsn"}

    for k, v in data.items():
        k_lower = k.lower()
        if any(sk in k_lower for sk in secret_keys):
            sanitized[k] = mask_secret(str(v)) if v else ""
        elif isinstance(v, dict):
            sanitized[k] = sanitize_for_logging(v)
        else:
            sanitized[k] = v
    return sanitized
