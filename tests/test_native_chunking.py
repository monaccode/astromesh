"""Tests that Rust and Python chunking produce identical results."""


class TestFixedChunker:
    def test_empty_document(self, use_native):
        from astromesh.rag.chunking.fixed import FixedChunker
        chunker = FixedChunker(chunk_size=100, overlap=10)
        assert chunker.chunk("", {}) == []

    def test_short_document(self, use_native):
        from astromesh.rag.chunking.fixed import FixedChunker
        chunker = FixedChunker(chunk_size=100, overlap=10)
        result = chunker.chunk("Hello world", {"source": "test"})
        assert len(result) == 1
        assert result[0]["content"] == "Hello world"
        assert result[0]["metadata"]["chunk_index"] == 0
        assert result[0]["metadata"]["strategy"] == "fixed"
        assert result[0]["metadata"]["source"] == "test"

    def test_exact_chunk_size(self, use_native):
        from astromesh.rag.chunking.fixed import FixedChunker
        chunker = FixedChunker(chunk_size=10, overlap=0)
        result = chunker.chunk("0123456789", {"src": "t"})
        assert len(result) == 1
        assert result[0]["content"] == "0123456789"

    def test_multiple_chunks_with_overlap(self, use_native):
        from astromesh.rag.chunking.fixed import FixedChunker
        text = "A" * 100
        chunker = FixedChunker(chunk_size=30, overlap=10)
        result = chunker.chunk(text, {})
        # Verify chunks cover the document
        assert len(result) >= 4
        for i, chunk in enumerate(result):
            assert chunk["metadata"]["chunk_index"] == i
            assert chunk["metadata"]["strategy"] == "fixed"
            assert len(chunk["content"]) <= 30

    def test_unicode(self, use_native):
        from astromesh.rag.chunking.fixed import FixedChunker
        # Unicode characters (emoji are multi-byte but single chars)
        text = "Hello " + "🌍" * 20
        chunker = FixedChunker(chunk_size=10, overlap=2)
        result = chunker.chunk(text, {})
        assert len(result) >= 2
        # Reconstruct should cover text (with overlaps)
        assert result[0]["content"][:6] == "Hello "


class TestRecursiveChunker:
    def test_empty(self, use_native):
        from astromesh.rag.chunking.recursive import RecursiveChunker
        chunker = RecursiveChunker(chunk_size=100)
        assert chunker.chunk("", {}) == []

    def test_short_text(self, use_native):
        from astromesh.rag.chunking.recursive import RecursiveChunker
        chunker = RecursiveChunker(chunk_size=100)
        result = chunker.chunk("Short text.", {})
        assert len(result) == 1
        assert result[0]["content"] == "Short text."

    def test_paragraph_split(self, use_native):
        from astromesh.rag.chunking.recursive import RecursiveChunker
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunker = RecursiveChunker(chunk_size=20, overlap=0)
        result = chunker.chunk(text, {"src": "t"})
        assert len(result) >= 2
        for chunk in result:
            assert chunk["metadata"]["strategy"] == "recursive"


class TestSentenceChunker:
    def test_empty(self, use_native):
        from astromesh.rag.chunking.sentence import SentenceChunker
        chunker = SentenceChunker(chunk_size=100)
        assert chunker.chunk("", {}) == []

    def test_single_sentence(self, use_native):
        from astromesh.rag.chunking.sentence import SentenceChunker
        chunker = SentenceChunker(chunk_size=100)
        result = chunker.chunk("Hello world.", {})
        assert len(result) == 1
        assert result[0]["content"] == "Hello world."

    def test_multiple_sentences(self, use_native):
        from astromesh.rag.chunking.sentence import SentenceChunker
        text = "First sentence. Second sentence. Third sentence."
        chunker = SentenceChunker(chunk_size=25)
        result = chunker.chunk(text, {})
        assert len(result) >= 2
        for chunk in result:
            assert chunk["metadata"]["strategy"] == "sentence"
