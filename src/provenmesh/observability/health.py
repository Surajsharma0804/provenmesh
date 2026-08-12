"""Health check endpoints for workers — Docker/K8s liveness and readiness probes."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


class HealthStatus:
    """Tracks worker health for liveness/readiness probes."""

    def __init__(self) -> None:
        self._ready = False
        self._alive = True
        self._last_heartbeat: datetime = datetime.now(UTC)
        self._items_processed: int = 0
        self._errors: int = 0
        self._current_state: str = "starting"
        self._checks: dict[str, bool] = {}

    def set_ready(self) -> None:
        self._ready = True
        self._current_state = "running"

    def set_not_ready(self) -> None:
        self._ready = False

    def set_shutting_down(self) -> None:
        self._alive = False
        self._ready = False
        self._current_state = "shutting_down"

    def heartbeat(self) -> None:
        self._last_heartbeat = datetime.now(UTC)

    def record_processed(self) -> None:
        self._items_processed += 1
        self.heartbeat()

    def record_error(self) -> None:
        self._errors += 1
        self.heartbeat()

    def add_check(self, name: str, healthy: bool) -> None:
        self._checks[name] = healthy

    @property
    def is_alive(self) -> bool:
        return self._alive

    @property
    def is_ready(self) -> bool:
        return self._ready and self._alive

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self.is_ready else "unhealthy",
            "alive": self._alive,
            "ready": self._ready,
            "state": self._current_state,
            "last_heartbeat": self._last_heartbeat.isoformat(),
            "items_processed": self._items_processed,
            "errors": self._errors,
            "checks": self._checks,
        }


async def start_health_server(
    health: HealthStatus,
    port: int = 8080,
) -> asyncio.AbstractServer:
    """Start an async HTTP health check server.

    Endpoints:
        GET /health   → 200 if alive, 503 otherwise
        GET /ready    → 200 if ready, 503 otherwise
        GET /metrics  → JSON status dump
    """

    async def handle_request(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            data = await asyncio.wait_for(reader.read(4096), timeout=5.0)
            request_line = data.decode("utf-8").split("\r\n")[0]
            path = request_line.split(" ")[1] if " " in request_line else "/"

            if path == "/health":
                status_code = 200 if health.is_alive else 503
                body = json.dumps({"alive": health.is_alive})
            elif path == "/ready":
                status_code = 200 if health.is_ready else 503
                body = json.dumps({"ready": health.is_ready})
            elif path == "/metrics":
                status_code = 200
                body = json.dumps(health.to_dict(), default=str)
            else:
                status_code = 404
                body = json.dumps({"error": "not found"})

            response = (
                f"HTTP/1.1 {status_code} OK\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"\r\n"
                f"{body}"
            )
            writer.write(response.encode())
            await writer.drain()
        except Exception:  # noqa: S110
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle_request, "0.0.0.0", port)  # noqa: S104
    logger.info("health_server_started", port=port)
    return server
