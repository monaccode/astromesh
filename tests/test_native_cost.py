"""Tests for native cost tracker."""
import pytest


class TestCostIndex:
    def test_record_and_total(self):
        try:
            from astromesh._native import RustCostIndex
            idx = RustCostIndex()
            idx.record("agent1", "s1", "gpt-4", "openai", 0.05, 100.0, 500, 200, 1000.0)
            idx.record("agent1", "s1", "gpt-4", "openai", 0.03, 80.0, 300, 100, 1001.0)
            assert abs(idx.total_cost(None, None, None) - 0.08) < 0.001
        except ImportError:
            pytest.skip("Native module not available")

    def test_filter_by_agent(self):
        try:
            from astromesh._native import RustCostIndex
            idx = RustCostIndex()
            idx.record("agent1", "s1", "gpt-4", "openai", 0.05, 100.0, 500, 200, 1000.0)
            idx.record("agent2", "s1", "gpt-4", "openai", 0.03, 80.0, 300, 100, 1001.0)
            assert abs(idx.total_cost("agent1", None, None) - 0.05) < 0.001
        except ImportError:
            pytest.skip("Native module not available")

    def test_group_by_provider(self):
        try:
            from astromesh._native import RustCostIndex
            idx = RustCostIndex()
            idx.record("a1", "s1", "gpt-4", "openai", 0.05, 100.0, 500, 200, 1000.0)
            idx.record("a1", "s1", "llama", "ollama", 0.01, 50.0, 100, 50, 1001.0)
            groups = idx.group_by(None, "provider")
            assert "openai" in groups
            assert "ollama" in groups
            assert groups["openai"][1] == 1  # calls count
        except ImportError:
            pytest.skip("Native module not available")
