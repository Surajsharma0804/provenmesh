"""Tests for observability/tracing.py — trace_operation context manager."""
from __future__ import annotations

from provenmesh.observability.logging import set_correlation_id
from provenmesh.observability.tracing import create_span_id, trace_operation


class TestTraceOperation:
    def test_basic_trace(self) -> None:
        set_correlation_id("")  # Reset to ensure fresh UUID is generated
        with trace_operation("test_op") as cid:
            assert len(cid) > 0
            assert isinstance(cid, str)

    def test_with_provided_correlation_id(self) -> None:
        with trace_operation("test_op", correlation_id="custom-123") as cid:
            assert cid == "custom-123"

    def test_preserves_previous_cid(self) -> None:
        set_correlation_id("original-cid")
        with trace_operation("test_op", correlation_id="temp-cid") as cid:
            assert cid == "temp-cid"

    def test_with_extra_kwargs(self) -> None:
        with trace_operation("fetch", url="https://test.com", retries=3) as cid:
            assert isinstance(cid, str)

    def test_exception_propagation(self) -> None:
        import pytest
        set_correlation_id("")
        with pytest.raises(ValueError, match="test"), trace_operation("failing_op"):
            raise ValueError("test")


class TestCreateSpanId:
    def test_length(self) -> None:
        span_id = create_span_id()
        assert len(span_id) == 16

    def test_uniqueness(self) -> None:
        span_ids = {create_span_id() for _ in range(100)}
        assert len(span_ids) == 100
