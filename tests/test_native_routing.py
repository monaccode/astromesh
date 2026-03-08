"""Tests for native routing helpers."""
import pytest


class TestRoutingHelpers:
    def test_ema_update(self):
        try:
            from astromesh._native import rust_ema_update
            result = rust_ema_update(100.0, 50.0, 0.8, 0.2)
            assert abs(result - 90.0) < 0.001
        except ImportError:
            pytest.skip("Native module not available")

    def test_detect_vision_no_images(self):
        try:
            from astromesh._native import rust_detect_vision
            messages = [{"role": "user", "content": "Hello"}]
            assert rust_detect_vision(messages) is False
        except ImportError:
            pytest.skip("Native module not available")

    def test_detect_vision_with_images(self):
        try:
            from astromesh._native import rust_detect_vision
            messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:..."}}]}]
            assert rust_detect_vision(messages) is True
        except ImportError:
            pytest.skip("Native module not available")

    def test_rank_cost_optimized(self):
        try:
            from astromesh._native import rust_rank_candidates
            providers = [
                ("expensive", 0.05, 100.0, False, 0.0, True, True),
                ("cheap", 0.01, 200.0, False, 0.0, True, True),
                ("mid", 0.03, 150.0, False, 0.0, True, True),
            ]
            result = rust_rank_candidates(providers, "cost_optimized", 0, False, False)
            assert result[0] == "cheap"
            assert result[-1] == "expensive"
        except ImportError:
            pytest.skip("Native module not available")

    def test_rank_latency_optimized(self):
        try:
            from astromesh._native import rust_rank_candidates
            providers = [
                ("slow", 0.01, 300.0, False, 0.0, True, True),
                ("fast", 0.05, 50.0, False, 0.0, True, True),
            ]
            result = rust_rank_candidates(providers, "latency_optimized", 0, False, False)
            assert result[0] == "fast"
        except ImportError:
            pytest.skip("Native module not available")
