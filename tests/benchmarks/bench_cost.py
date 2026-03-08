"""Benchmarks for cost tracker."""
import pytest


@pytest.mark.benchmark
class TestCostBenchmark:
    @pytest.fixture(params=[1000, 10000, 100000], ids=["1K-records", "10K-records", "100K-records"])
    def index(self, request):
        try:
            from astromesh._native import RustCostIndex
        except ImportError:
            pytest.skip("Native module not available")
        idx = RustCostIndex()
        for i in range(request.param):
            idx.record(
                f"agent_{i % 5}", f"session_{i % 20}", f"model_{i % 3}",
                f"provider_{i % 4}", 0.001 * i, 100.0, 500, 200, 1000.0 + i
            )
        return idx

    def test_total_cost(self, benchmark, index):
        benchmark(index.total_cost, "agent_1", None, None)

    def test_group_by(self, benchmark, index):
        benchmark(index.group_by, None, "provider")
