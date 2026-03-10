"""Tests for RAG wrapper tools: rag_query, rag_ingest."""

from unittest.mock import AsyncMock, MagicMock
from astromesh.tools.base import ToolContext


def _ctx(**kwargs):
    return ToolContext(agent_name="test", session_id="s1", **kwargs)


class TestRagQueryTool:
    async def test_query_without_pipeline(self):
        from astromesh.tools.builtin.rag import RagQueryTool

        tool = RagQueryTool()
        result = await tool.execute({"query": "test"}, _ctx())
        assert result.success is False
        assert "pipeline" in result.error.lower()

    async def test_query_with_pipeline(self):
        from astromesh.tools.builtin.rag import RagQueryTool

        mock_pipeline = MagicMock()
        mock_pipeline.query = AsyncMock(return_value=[{"text": "Result doc", "score": 0.9}])
        ctx = _ctx()
        ctx.rag_pipeline = mock_pipeline

        tool = RagQueryTool()
        result = await tool.execute({"query": "find something", "top_k": 3}, ctx)
        assert result.success is True
        assert result.data["results"] == [{"text": "Result doc", "score": 0.9}]
        mock_pipeline.query.assert_called_once_with("find something", top_k=3)

    async def test_query_default_top_k(self):
        from astromesh.tools.builtin.rag import RagQueryTool

        mock_pipeline = MagicMock()
        mock_pipeline.query = AsyncMock(return_value=[])
        ctx = _ctx()
        ctx.rag_pipeline = mock_pipeline

        tool = RagQueryTool()
        result = await tool.execute({"query": "search"}, ctx)
        assert result.success is True
        mock_pipeline.query.assert_called_once_with("search", top_k=5)

    async def test_query_pipeline_exception(self):
        from astromesh.tools.builtin.rag import RagQueryTool

        mock_pipeline = MagicMock()
        mock_pipeline.query = AsyncMock(side_effect=RuntimeError("pipeline error"))
        ctx = _ctx()
        ctx.rag_pipeline = mock_pipeline

        tool = RagQueryTool()
        result = await tool.execute({"query": "bad query"}, ctx)
        assert result.success is False
        assert "pipeline error" in result.error


class TestRagIngestTool:
    async def test_ingest_without_pipeline(self):
        from astromesh.tools.builtin.rag import RagIngestTool

        tool = RagIngestTool()
        result = await tool.execute({"document": "content", "metadata": {}}, _ctx())
        assert result.success is False
        assert "pipeline" in result.error.lower()

    async def test_ingest_with_pipeline(self):
        from astromesh.tools.builtin.rag import RagIngestTool

        mock_pipeline = MagicMock()
        mock_pipeline.ingest = AsyncMock(return_value=None)
        ctx = _ctx()
        ctx.rag_pipeline = mock_pipeline

        tool = RagIngestTool()
        result = await tool.execute(
            {"document": "doc content", "metadata": {"source": "test"}}, ctx
        )
        assert result.success is True
        assert result.data["ingested"] is True
        mock_pipeline.ingest.assert_called_once_with("doc content", metadata={"source": "test"})

    async def test_ingest_default_empty_metadata(self):
        from astromesh.tools.builtin.rag import RagIngestTool

        mock_pipeline = MagicMock()
        mock_pipeline.ingest = AsyncMock(return_value=None)
        ctx = _ctx()
        ctx.rag_pipeline = mock_pipeline

        tool = RagIngestTool()
        result = await tool.execute({"document": "some text"}, ctx)
        assert result.success is True
        mock_pipeline.ingest.assert_called_once_with("some text", metadata={})

    async def test_ingest_pipeline_exception(self):
        from astromesh.tools.builtin.rag import RagIngestTool

        mock_pipeline = MagicMock()
        mock_pipeline.ingest = AsyncMock(side_effect=ValueError("ingest failed"))
        ctx = _ctx()
        ctx.rag_pipeline = mock_pipeline

        tool = RagIngestTool()
        result = await tool.execute({"document": "text"}, ctx)
        assert result.success is False
        assert "ingest failed" in result.error
