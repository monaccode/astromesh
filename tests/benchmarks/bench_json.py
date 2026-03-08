"""Benchmarks for JSON parsing."""
import json
import pytest


@pytest.mark.benchmark
class TestJsonBenchmark:
    @pytest.fixture
    def json_text(self):
        data = {
            "steps": [
                {"step": i, "description": f"Do task {i}", "tool": None, "depends_on": []}
                for i in range(20)
            ],
            "metadata": {"model": "gpt-4", "tokens": 1500},
        }
        return json.dumps(data)

    def test_native(self, benchmark, json_text):
        try:
            from astromesh._native import rust_json_loads
        except ImportError:
            pytest.skip("Native module not available")
        benchmark(rust_json_loads, json_text)

    def test_python(self, benchmark, json_text):
        benchmark(json.loads, json_text)
