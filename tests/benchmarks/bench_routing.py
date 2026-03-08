"""Benchmarks for routing helpers."""
import pytest


@pytest.mark.benchmark
class TestRoutingBenchmark:
    @pytest.fixture(params=[5, 20, 50], ids=["5-providers", "20-providers", "50-providers"])
    def providers(self, request):
        n = request.param
        return [
            (f"provider_{i}", 0.01 * (i + 1), 100.0 * (n - i), False, 0.0, True, True)
            for i in range(n)
        ]

    def test_native(self, benchmark, providers):
        try:
            from astromesh._native import rust_rank_candidates
        except ImportError:
            pytest.skip("Native module not available")
        benchmark(rust_rank_candidates, providers, "cost_optimized", 0, False, False)
