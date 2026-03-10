"""AI built-in tools: text_summarize."""

from __future__ import annotations

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult

_MIN_SUMMARIZE_LENGTH = 500


class TextSummarizeTool(BuiltinTool):
    name = "text_summarize"
    description = "Summarize long text using the agent's language model"
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "max_length": {"type": "integer", "default": 200},
        },
        "required": ["text"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        text = arguments["text"]
        max_length = arguments.get("max_length", 200)

        if len(text) < _MIN_SUMMARIZE_LENGTH:
            return ToolResult(
                success=True,
                data={"summary": text, "was_summarized": False},
                metadata={},
            )

        model_fn = getattr(context, "model_fn", None)
        if model_fn is None:
            return ToolResult(
                success=False,
                data=None,
                error="text_summarize requires model access (model_fn not available)",
            )

        try:
            messages = [{"role": "user", "content": f"Summarize in ~{max_length} words:\n\n{text}"}]
            response = await model_fn(messages, [])
            summary = response.get("content", "")
            usage = response.get("usage", {})
            return ToolResult(
                success=True,
                data={"summary": summary, "was_summarized": True},
                metadata={
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                },
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
