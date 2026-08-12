"""Tests for observability/health.py — HealthStatus tracking."""
from __future__ import annotations

from provenmesh.observability.health import HealthStatus


class TestHealthStatus:
    def test_initial_state(self) -> None:
        h = HealthStatus()
        assert h.is_alive is True
        assert h.is_ready is False
        assert h.to_dict()["state"] == "starting"

    def test_set_ready(self) -> None:
        h = HealthStatus()
        h.set_ready()
        assert h.is_ready is True
        assert h.to_dict()["state"] == "running"

    def test_set_not_ready(self) -> None:
        h = HealthStatus()
        h.set_ready()
        h.set_not_ready()
        assert h.is_ready is False

    def test_set_shutting_down(self) -> None:
        h = HealthStatus()
        h.set_ready()
        h.set_shutting_down()
        assert h.is_alive is False
        assert h.is_ready is False
        assert h.to_dict()["state"] == "shutting_down"

    def test_heartbeat(self) -> None:
        h = HealthStatus()
        first_hb = h.to_dict()["last_heartbeat"]
        h.heartbeat()
        second_hb = h.to_dict()["last_heartbeat"]
        assert second_hb >= first_hb

    def test_record_processed(self) -> None:
        h = HealthStatus()
        h.record_processed()
        h.record_processed()
        assert h.to_dict()["items_processed"] == 2

    def test_record_error(self) -> None:
        h = HealthStatus()
        h.record_error()
        assert h.to_dict()["errors"] == 1

    def test_add_check(self) -> None:
        h = HealthStatus()
        h.add_check("redis", True)
        h.add_check("postgres", False)
        checks = h.to_dict()["checks"]
        assert checks["redis"] is True
        assert checks["postgres"] is False

    def test_to_dict_complete(self) -> None:
        h = HealthStatus()
        h.set_ready()
        d = h.to_dict()
        assert d["status"] == "healthy"
        assert d["alive"] is True
        assert d["ready"] is True
        assert "last_heartbeat" in d
        assert "items_processed" in d
        assert "errors" in d
        assert "checks" in d
