"""Tests for AI tool: text_summarize."""

from unittest.mock import AsyncMock
from astromesh.tools.base import ToolContext


def _ctx(**kwargs):
    return ToolContext(agent_name="test", session_id="s1", **kwargs)


class TestTextSummarizeTool:
    async def test_summarize(self):
        from astromesh.tools.builtin.ai import TextSummarizeTool

        tool = TextSummarizeTool()
        mock_model_fn = AsyncMock(
            return_value={
                "content": "Summary.",
                "usage": {"input_tokens": 100, "output_tokens": 20},
            }
        )
        ctx = _ctx()
        ctx.model_fn = mock_model_fn
        result = await tool.execute({"text": "A very long text. " * 50, "max_length": 100}, ctx)
        assert result.success is True
        assert "summary" in result.data

    async def test_short_text_returned_as_is(self):
        from astromesh.tools.builtin.ai import TextSummarizeTool

        tool = TextSummarizeTool()
        result = await tool.execute({"text": "Short text."}, _ctx())
        assert result.success is True
        assert result.data["summary"] == "Short text."
        assert result.data["was_summarized"] is False

    async def test_no_model_fn_returns_error(self):
        from astromesh.tools.builtin.ai import TextSummarizeTool

        tool = TextSummarizeTool()
        # Long text but no model_fn in context
        result = await tool.execute({"text": "x " * 300}, _ctx())
        assert result.success is False
        assert "model_fn" in result.error or "model" in result.error.lower()

    async def test_summarize_uses_max_length_param(self):
        from astromesh.tools.builtin.ai import TextSummarizeTool

        tool = TextSummarizeTool()
        mock_model_fn = AsyncMock(return_value={"content": "Short summary.", "usage": {}})
        ctx = _ctx()
        ctx.model_fn = mock_model_fn
        result = await tool.execute({"text": "long text " * 60, "max_length": 50}, ctx)
        assert result.success is True
        # Verify model_fn was called with a message containing the max_length hint
        call_args = mock_model_fn.call_args
        assert "50" in call_args[0][0][0]["content"]

    async def test_summarize_metadata_has_token_counts(self):
        from astromesh.tools.builtin.ai import TextSummarizeTool

        tool = TextSummarizeTool()
        mock_model_fn = AsyncMock(
            return_value={
                "content": "Summary here.",
                "usage": {"input_tokens": 200, "output_tokens": 30},
            }
        )
        ctx = _ctx()
        ctx.model_fn = mock_model_fn
        result = await tool.execute({"text": "word " * 120}, ctx)
        assert result.success is True
        assert result.metadata["input_tokens"] == 200
        assert result.metadata["output_tokens"] == 30

    async def test_summarize_model_fn_exception(self):
        from astromesh.tools.builtin.ai import TextSummarizeTool

        tool = TextSummarizeTool()
        mock_model_fn = AsyncMock(side_effect=RuntimeError("model failure"))
        ctx = _ctx()
        ctx.model_fn = mock_model_fn
        result = await tool.execute({"text": "word " * 120}, ctx)
        assert result.success is False
        assert "model failure" in result.error

    async def test_was_summarized_flag_true_for_long_text(self):
        from astromesh.tools.builtin.ai import TextSummarizeTool

        tool = TextSummarizeTool()
        mock_model_fn = AsyncMock(return_value={"content": "Summary.", "usage": {}})
        ctx = _ctx()
        ctx.model_fn = mock_model_fn
        result = await tool.execute({"text": "A long text. " * 50}, ctx)
        assert result.data["was_summarized"] is True
