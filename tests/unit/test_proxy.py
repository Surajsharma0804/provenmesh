"""Tests for crawler/proxy.py — ProxyPool and ProxyStats."""
from __future__ import annotations

from provenmesh.crawler.proxy import ProxyPool, ProxyStats


class TestProxyStats:
    def test_initial_state(self) -> None:
        stats = ProxyStats()
        assert stats.total == 0
        assert stats.success_rate == 1.0

    def test_after_successes(self) -> None:
        stats = ProxyStats(successes=8, failures=2)
        assert stats.total == 10
        assert stats.success_rate == 0.8

    def test_all_failures(self) -> None:
        stats = ProxyStats(successes=0, failures=5)
        assert stats.success_rate == 0.0


class TestProxyPool:
    def test_empty_pool_returns_none(self) -> None:
        pool = ProxyPool()
        assert pool.get_proxy("example.com") is None

    def test_add_proxy(self) -> None:
        pool = ProxyPool()
        pool.add_proxy("http://proxy1:8080")
        assert len(pool.proxies) == 1

    def test_add_duplicate_proxy(self) -> None:
        pool = ProxyPool()
        pool.add_proxy("http://proxy1:8080")
        pool.add_proxy("http://proxy1:8080")
        assert len(pool.proxies) == 1

    def test_add_empty_proxy(self) -> None:
        pool = ProxyPool()
        pool.add_proxy("")
        assert len(pool.proxies) == 0

    def test_sticky_assignment(self) -> None:
        pool = ProxyPool()
        pool.add_proxy("http://proxy1:8080")
        p1 = pool.get_proxy("example.com")
        p2 = pool.get_proxy("example.com")
        assert p1 == p2

    def test_record_success(self) -> None:
        pool = ProxyPool()
        pool.add_proxy("http://proxy1:8080")
        pool.record_success("http://proxy1:8080")
        stats = pool.get_stats()
        assert len(stats) == 1

    def test_record_failure_and_rotation(self) -> None:
        pool = ProxyPool()
        pool.add_proxy("http://proxy1:8080")
        pool.add_proxy("http://proxy2:8080")
        proxy = pool.get_proxy("test.com")
        # Record enough failures to drop below threshold
        for _ in range(10):
            pool.record_failure(proxy, "test.com")
        # Should rotate to a different proxy
        new_proxy = pool.get_proxy("test.com")
        assert new_proxy is not None

    def test_get_stats(self) -> None:
        pool = ProxyPool()
        pool.add_proxy("http://proxy1:8080")
        pool.record_success("http://proxy1:8080")
        stats = pool.get_stats()
        key = next(iter(stats.keys()))
        assert "success_rate" in stats[key]
        assert "total_requests" in stats[key]

    def test_sticky_rotation_on_failure(self) -> None:
        """When a proxy drops below min_success_rate, the sticky
        assignment is cleared and a different proxy is selected."""
        pool = ProxyPool()
        pool.add_proxy("http://proxy1:8080")
        pool.add_proxy("http://proxy2:8080")
        # Assign sticky to proxy1
        pool.get_proxy("example.com")
        # Fail proxy1 many times
        for _ in range(20):
            pool.record_failure("http://proxy1:8080", "example.com")
        # Next request should NOT return the failed proxy
        proxy = pool.get_proxy("example.com")
        assert proxy is not None

    def test_record_failure_deprioritizes(self) -> None:
        """record_failure should clear sticky assignment when below threshold."""
        pool = ProxyPool()
        pool.add_proxy("http://proxy1:8080")
        pool.get_proxy("test.com")  # Assign sticky
        # 10 failures, 0 successes → success_rate = 0.0
        for _ in range(10):
            pool.record_failure("http://proxy1:8080", "test.com")
        # Sticky should be cleared
        assert "test.com" not in pool._domain_assignments

    def test_get_proxy_rotates_degraded_sticky(self) -> None:
        """When get_proxy finds a sticky proxy with low success_rate,
        it deletes the assignment and rotates (line 72)."""
        pool = ProxyPool()
        pool.add_proxy("http://proxy1:8080")
        pool.add_proxy("http://proxy2:8080")
        # Directly set sticky assignment to proxy1
        pool._domain_assignments["example.com"] = "http://proxy1:8080"
        # Degrade proxy1 stats directly
        pool._stats["http://proxy1:8080"].failures = 100
        pool._stats["http://proxy1:8080"].successes = 0
        # Verify proxy1 is below threshold
        assert pool._stats["http://proxy1:8080"].success_rate < pool._min_success_rate
        # get_proxy should trigger line 72 (del assignment) then re-assign
        new_proxy = pool.get_proxy("example.com")
        assert new_proxy is not None


class TestGetProxyPool:
    def test_get_proxy_pool_singleton(self) -> None:
        from provenmesh.crawler import proxy
        # Reset singleton
        proxy._proxy_pool = None
        pool = proxy.get_proxy_pool()
        assert isinstance(pool, ProxyPool)
        # Second call returns same instance
        pool2 = proxy.get_proxy_pool()
        assert pool is pool2
        # Cleanup
        proxy._proxy_pool = None

