"""Built-in tool implementations for Astromesh."""

from astromesh.tools.builtin.utilities import (
    DatetimeNowTool,
    JsonTransformTool,
    CacheStoreTool,
)
from astromesh.tools.builtin.http import HttpRequestTool, GraphQLQueryTool
from astromesh.tools.builtin.web_search import WebSearchTool, WebScrapeTool, WikipediaTool
from astromesh.tools.builtin.files import ReadFileTool, WriteFileTool
from astromesh.tools.builtin.database import SqlQueryTool
from astromesh.tools.builtin.communication import (
    SendWebhookTool,
    SendSlackTool,
    SendEmailTool,
)
from astromesh.tools.builtin.ai import TextSummarizeTool
from astromesh.tools.builtin.rag import RagQueryTool, RagIngestTool

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
