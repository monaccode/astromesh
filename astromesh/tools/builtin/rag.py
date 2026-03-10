"""RAG wrapper built-in tools: rag_query, rag_ingest."""

from __future__ import annotations

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult


class RagQueryTool(BuiltinTool):
    name = "rag_query"
    description = "Query the RAG pipeline for relevant documents"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        pipeline = getattr(context, "rag_pipeline", None)
        if pipeline is None:
            return ToolResult(
                success=False, data=None, error="RAG pipeline not available in context"
            )
        try:
            results = await pipeline.query(arguments["query"], top_k=arguments.get("top_k", 5))
            return ToolResult(success=True, data={"results": results}, metadata={})
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class RagIngestTool(BuiltinTool):
    name = "rag_ingest"
    description = "Ingest a document into the RAG pipeline"
    parameters = {
        "type": "object",
        "properties": {
            "document": {"type": "string"},
            "metadata": {"type": "object"},
        },
        "required": ["document"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        pipeline = getattr(context, "rag_pipeline", None)
        if pipeline is None:
            return ToolResult(
                success=False, data=None, error="RAG pipeline not available in context"
            )
        try:
            await pipeline.ingest(arguments["document"], metadata=arguments.get("metadata", {}))
            return ToolResult(success=True, data={"ingested": True}, metadata={})
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
