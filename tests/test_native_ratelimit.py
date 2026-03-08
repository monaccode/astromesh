"""Tests for native rate limiter."""
import pytest


class TestRateLimiter:
    def test_within_limit(self):
        """Test that calls within the limit are allowed."""
        try:
            from astromesh._native import RustRateLimiter
            rl = RustRateLimiter()
            for _ in range(5):
                assert rl.check("tool1", 60.0, 10) is True
        except ImportError:
            pytest.skip("Native module not available")

    def test_exceeds_limit(self):
        """Test that calls exceeding the limit are blocked."""
        try:
            from astromesh._native import RustRateLimiter
            rl = RustRateLimiter()
            for _ in range(10):
                rl.check("tool1", 60.0, 10)
            assert rl.check("tool1", 60.0, 10) is False
        except ImportError:
            pytest.skip("Native module not available")

    def test_different_tools(self):
        """Test that different tools have independent limits."""
        try:
            from astromesh._native import RustRateLimiter
            rl = RustRateLimiter()
            for _ in range(10):
                rl.check("tool1", 60.0, 10)
            # tool2 should still be allowed
            assert rl.check("tool2", 60.0, 10) is True
        except ImportError:
            pytest.skip("Native module not available")
