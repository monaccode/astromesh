"""Built-in tool implementations for Astromesh."""

from astromesh.tools.builtin.ai import TextSummarizeTool
from astromesh.tools.builtin.communication import (
    SendEmailTool,
    SendSlackTool,
    SendWebhookTool,
)
from astromesh.tools.builtin.database import SqlQueryTool
from astromesh.tools.builtin.files import ReadFileTool, WriteFileTool
from astromesh.tools.builtin.http import GraphQLQueryTool, HttpRequestTool
from astromesh.tools.builtin.rag import RagIngestTool, RagQueryTool
from astromesh.tools.builtin.utilities import (
    CacheStoreTool,
    DatetimeNowTool,
    JsonTransformTool,
)
from astromesh.tools.builtin.web_search import WebScrapeTool, WebSearchTool, WikipediaTool

ALL_TOOLS: list = [
    DatetimeNowTool,
    JsonTransformTool,
    CacheStoreTool,
    HttpRequestTool,
    GraphQLQueryTool,
    WebSearchTool,
    WebScrapeTool,
    WikipediaTool,
    ReadFileTool,
    WriteFileTool,
    SqlQueryTool,
    SendWebhookTool,
    SendSlackTool,
    SendEmailTool,
    TextSummarizeTool,
    RagQueryTool,
    RagIngestTool,
]
