"""Benchmarks for rate limiter."""
import pytest


@pytest.mark.benchmark
class TestRateLimiterBenchmark:
    @pytest.fixture(params=[100, 1000, 10000], ids=["100-calls", "1000-calls", "10000-calls"])
    def n_calls(self, request):
        return request.param

    def test_native(self, benchmark, n_calls):
        try:
            from astromesh._native import RustRateLimiter
        except ImportError:
            pytest.skip("Native module not available")
        rl = RustRateLimiter()
        def run():
            for i in range(n_calls):
                rl.check(f"tool_{i % 10}", 3600.0, n_calls)
        benchmark(run)
