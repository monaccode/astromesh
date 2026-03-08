"""Benchmarks for guardrails."""
import os
import pytest


def make_pii_text(density="low"):
    base = "This is a sample text with some content. "
    pii = "Contact john@example.com or call 555-123-4567. SSN: 123-45-6789. Card: 4111 1111 1111 1111. "
    if density == "low":
        return (base * 20) + pii
    elif density == "medium":
        return (base * 5 + pii) * 10
    else:
        return (base + pii) * 50


@pytest.mark.benchmark
class TestPiiRedactionBenchmark:
    @pytest.fixture(params=["low", "medium", "high"], ids=["low-pii", "med-pii", "high-pii"])
    def text(self, request):
        return make_pii_text(request.param)

    def test_native(self, benchmark, text):
        os.environ.pop("ASTROMESH_FORCE_PYTHON", None)
        from astromesh.core.guardrails import GuardrailsEngine
        engine = GuardrailsEngine()
        benchmark(engine._redact_pii, text, "redact")

    def test_python(self, benchmark, text):
        os.environ["ASTROMESH_FORCE_PYTHON"] = "1"
        from astromesh.core.guardrails import GuardrailsEngine
        engine = GuardrailsEngine()
        benchmark(engine._redact_pii, text, "redact")
