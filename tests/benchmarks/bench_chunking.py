"""Benchmarks for chunking strategies."""
import os
import pytest


def make_text(size_bytes):
    """Generate text of approximately the given size."""
    sentence = "The quick brown fox jumps over the lazy dog. "
    repeats = size_bytes // len(sentence) + 1
    return (sentence * repeats)[:size_bytes]


@pytest.mark.benchmark
class TestFixedChunkerBenchmark:
    @pytest.fixture(params=[1000, 100_000, 1_000_000], ids=["1KB", "100KB", "1MB"])
    def text(self, request):
        return make_text(request.param)

    def test_native(self, benchmark, text):
        os.environ.pop("ASTROMESH_FORCE_PYTHON", None)
        from astromesh.rag.chunking.fixed import FixedChunker
        chunker = FixedChunker(chunk_size=500, overlap=50)
        benchmark(chunker.chunk, text, {"source": "bench"})

    def test_python(self, benchmark, text):
        os.environ["ASTROMESH_FORCE_PYTHON"] = "1"
        from astromesh.rag.chunking.fixed import FixedChunker
        chunker = FixedChunker(chunk_size=500, overlap=50)
        benchmark(chunker.chunk, text, {"source": "bench"})


@pytest.mark.benchmark
class TestSentenceChunkerBenchmark:
    @pytest.fixture(params=[1000, 100_000], ids=["1KB", "100KB"])
    def text(self, request):
        return make_text(request.param)

    def test_native(self, benchmark, text):
        os.environ.pop("ASTROMESH_FORCE_PYTHON", None)
        from astromesh.rag.chunking.sentence import SentenceChunker
        chunker = SentenceChunker(chunk_size=500)
        benchmark(chunker.chunk, text, {"source": "bench"})

    def test_python(self, benchmark, text):
        os.environ["ASTROMESH_FORCE_PYTHON"] = "1"
        from astromesh.rag.chunking.sentence import SentenceChunker
        chunker = SentenceChunker(chunk_size=500)
        benchmark(chunker.chunk, text, {"source": "bench"})
