"""Tests for security/secrets.py — secret management and sanitization."""
from __future__ import annotations

from pydantic import SecretStr

from provenmesh.security.secrets import (
    get_secret,
    mask_secret,
    redact_secrets,
    safe_str,
    sanitize_for_logging,
    validate_required_secrets,
)


class TestGetSecret:
    def test_existing_env_var(self, monkeypatch) -> None:
        monkeypatch.setenv("TEST_SECRET_KEY", "my_secret_value")
        assert get_secret("TEST_SECRET_KEY") == "my_secret_value"

    def test_missing_env_var(self) -> None:
        result = get_secret("NONEXISTENT_KEY_XYZ", "default_val")
        assert result == "default_val"

    def test_missing_without_default(self) -> None:
        result = get_secret("NONEXISTENT_KEY_ABC")
        assert result == ""


class TestMaskSecret:
    def test_normal_secret(self) -> None:
        assert mask_secret("my_secret_key_12345") == "my_s***************"

    def test_short_secret(self) -> None:
        assert mask_secret("abc") == "****"

    def test_empty_secret(self) -> None:
        assert mask_secret("") == "****"

    def test_custom_visible_chars(self) -> None:
        assert mask_secret("abcdefgh", visible_chars=2) == "ab******"


class TestRedactSecrets:
    def test_redacts_api_key(self) -> None:
        text = "Using api_key=sk-12345abc for auth"
        result = redact_secrets(text)
        assert "sk-12345abc" not in result
        assert "[REDACTED]" in result

    def test_redacts_token(self) -> None:
        text = "bearer token: ghp_abc123"
        result = redact_secrets(text)
        assert "[REDACTED]" in result

    def test_safe_text_unchanged(self) -> None:
        text = "This is a normal log message"
        assert redact_secrets(text) == text


class TestSafeStr:
    def test_secret_str(self) -> None:
        s = SecretStr("my_secret")
        assert safe_str(s) == "my_secret"

    def test_plain_string(self) -> None:
        assert safe_str("plain") == "plain"

    def test_none(self) -> None:
        assert safe_str(None) == ""


class TestValidateRequiredSecrets:
    def test_present_secrets(self, monkeypatch) -> None:
        monkeypatch.setenv("KEY_A", "value_a")
        monkeypatch.setenv("KEY_B", "value_b")
        status = validate_required_secrets(["KEY_A", "KEY_B"])
        assert status["KEY_A"] is True
        assert status["KEY_B"] is True

    def test_missing_secrets(self) -> None:
        status = validate_required_secrets(["NONEXISTENT_XYZ_123"])
        assert status["NONEXISTENT_XYZ_123"] is False

    def test_placeholder_secrets(self, monkeypatch) -> None:
        monkeypatch.setenv("KEY_C", "your_key_here")
        status = validate_required_secrets(["KEY_C"])
        assert status["KEY_C"] is False


class TestSanitizeForLogging:
    def test_masks_secret_keys(self) -> None:
        data = {"api_key": "sk-12345", "name": "test"}
        result = sanitize_for_logging(data)
        assert result["name"] == "test"
        assert "sk-1" in result["api_key"]
        assert "12345" not in result["api_key"]

    def test_nested_dict(self) -> None:
        data = {"config": {"password": "secret123", "host": "localhost"}}
        result = sanitize_for_logging(data)
        assert result["config"]["host"] == "localhost"
        assert "secret123" not in str(result["config"]["password"])

    def test_empty_secret_value(self) -> None:
        data = {"token": ""}
        result = sanitize_for_logging(data)
        assert result["token"] == ""
