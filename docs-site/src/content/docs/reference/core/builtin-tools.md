---
title: Built-in Tools
description: 17 ready-to-use tools for common agent tasks
---

Astromesh ships with 17 built-in tools that cover common agent needs. They are implemented as Python classes extending `BuiltinTool` and registered via `type: builtin` in agent YAML. No external dependencies are needed for most tools.

## Quick Reference

| Tool | Category | Description |
|------|----------|-------------|
| `datetime_now` | Utilities | Current date/time with timezone |
| `json_transform` | Utilities | Transform JSON via Jinja2 template |
| `cache_store` | Utilities | Key-value cache between tool calls |
| `http_request` | HTTP | HTTP requests (GET/POST/PUT/DELETE/PATCH) |
| `graphql_query` | HTTP | GraphQL queries |
| `web_search` | Web | Search via Tavily API |
| `web_scrape` | Web | Extract text from URLs |
| `wikipedia` | Web | Wikipedia article summaries |
| `read_file` | Files | Read local files |
| `write_file` | Files | Write local files |
| `sql_query` | Database | SQL queries (SQLite, read-only default) |
| `send_webhook` | Communication | POST to webhook URLs |
| `send_slack` | Communication | Slack messages via webhook |
| `send_email` | Communication | Email via SMTP |
| `text_summarize` | AI | Summarize text via agent's model |
| `rag_query` | RAG | Query RAG pipeline |
| `rag_ingest` | RAG | Ingest into RAG pipeline |

## Using Built-in Tools

Register built-in tools in your agent YAML under `spec.tools` with `type: builtin`:

```yaml
spec:
  tools:
    - name: web_search
      type: builtin
      config:
        provider: tavily
        api_key: ${TAVILY_API_KEY}
    - name: http_request
      type: builtin
      config:
        allow_localhost: false
        timeout_seconds: 30
    - name: sql_query
      type: builtin
      config:
        connection_string: "sqlite:///data/app.db"
        read_only: true
```

Each tool defines its own `config` options. Secrets can be passed via `config` fields with `${ENV_VAR}` substitution or through `context.secrets`.

## API Discovery

List all available built-in tools and their schemas via the REST API:

```
GET /v1/tools/builtin
```

The response includes each tool's name, description, and parameter schema in OpenAI function calling format.

## Utility Tools

### datetime_now

Returns the current date and time.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `timezone` | string | No | IANA timezone name (e.g. `America/New_York`). Falls back to UTC on invalid timezone |

**Returns:** `{ datetime, timezone, unix_timestamp }`

### json_transform

Transforms a JSON value using a Jinja2 template.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `data` | any | Yes | Input data accessible as `{{ data }}` in the template |
| `template` | string | Yes | Jinja2 template that outputs JSON. Use `{{ data.field }}` to access nested values |

**Returns:** Parsed JSON from the rendered template output.

### cache_store

Key-value cache shared across tool calls within a session. Uses the `ToolContext.cache` dict.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | One of `get`, `set`, or `delete` |
| `key` | string | Yes | Cache key |
| `value` | any | No | Value to store (required for `set`) |

## HTTP Tools

### http_request

Makes HTTP requests to external services.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `method` | string | Yes | HTTP method: `GET`, `POST`, `PUT`, `DELETE`, or `PATCH` |
| `url` | string | Yes | Target URL |
| `headers` | object | No | Request headers |
| `body` | any | No | Request body (JSON-serialized) |

**Config options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `allow_localhost` | bool | `false` | Whether to permit requests to `localhost`, `127.0.0.1`, `0.0.0.0`, and `::1` |
| `timeout_seconds` | int | `30` | Request timeout |
| `max_response_bytes` | int | `5242880` | Maximum response size (5 MB) |

### graphql_query

Executes GraphQL queries against a remote endpoint.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `endpoint` | string | Yes | GraphQL endpoint URL |
| `query` | string | Yes | GraphQL query or mutation |
| `variables` | object | No | Query variables |
| `headers` | object | No | Request headers |

**Config options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `timeout_seconds` | int | `30` | Request timeout |

## Web Tools

### web_search

Searches the web using a search provider.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search query |
| `max_results` | int | No | Maximum number of results to return |

**Config options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `provider` | string | `tavily` | Search provider |
| `api_key` | string | -- | API key (or set `SEARCH_API_KEY` secret) |

**Returns:** Array of search results with title, URL, and snippet.

### web_scrape

Extracts text content from a URL by stripping HTML tags, scripts, and styles.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL to scrape |
| `max_length` | int | No | Maximum character length of extracted text. Default: `10000` |

Follows redirects automatically.

### wikipedia

Fetches Wikipedia article summaries via the Wikipedia REST API.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `topic` | string | Yes | Article topic to look up |
| `language` | string | No | Wikipedia language code. Default: `en` |

## File Tools

### read_file

Reads a file from the local filesystem.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | File path to read |
| `encoding` | string | No | File encoding. Default: `utf-8` |

**Config options:**

| Option | Type | Description |
|--------|------|-------------|
| `allowed_paths` | list | List of directory prefixes the tool is allowed to read from. Access outside these paths is blocked |

### write_file

Writes content to a file on the local filesystem. Creates parent directories automatically if they do not exist.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | File path to write |
| `content` | string | Yes | Content to write |
| `encoding` | string | No | File encoding. Default: `utf-8` |

**Config options:**

| Option | Type | Description |
|--------|------|-------------|
| `allowed_paths` | list | List of directory prefixes the tool is allowed to write to. Access outside these paths is blocked |

## Database Tools

### sql_query

Executes SQL queries against a database. Currently supports SQLite.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | SQL query to execute |
| `params` | list | No | Parameterized query values |

**Config options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `connection_string` | string | -- | Database connection string (required). e.g. `sqlite:///data/app.db` |
| `read_only` | bool | `true` | Block write operations. When enabled, `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, and `TRUNCATE` statements are rejected |
| `max_rows` | int | `1000` | Maximum rows returned per query |

## Communication Tools

### send_webhook

Sends a POST request with a JSON body to a webhook URL.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | Webhook URL |
| `payload` | any | Yes | JSON payload |
| `headers` | object | No | Additional request headers |

### send_slack

Sends a message to Slack via an incoming webhook.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | Yes | Message text |
| `channel` | string | No | Channel override |

**Config options:**

| Option | Type | Description |
|--------|------|-------------|
| `webhook_url` | string | Slack incoming webhook URL (or set `SLACK_WEBHOOK_URL` secret) |

### send_email

Sends an email via SMTP. Uses `asyncio.to_thread()` internally to avoid blocking the event loop.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `to` | string | Yes | Recipient email address |
| `subject` | string | Yes | Email subject |
| `body` | string | Yes | Email body |

**Config options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `smtp_host` | string | -- | SMTP server hostname |
| `smtp_port` | int | `587` | SMTP server port |
| `smtp_user` | string | -- | SMTP username |
| `smtp_password` | string | -- | SMTP password |
| `from_address` | string | -- | Sender email address |

## AI Tools

### text_summarize

Summarizes text using the agent's configured model. If the input text is shorter than 500 characters, it is returned as-is with `was_summarized: false`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `text` | string | Yes | Text to summarize |
| `max_length` | int | No | Target summary length |

## RAG Tools

### rag_query

Queries the RAG pipeline attached to the agent's context. Requires a RAG pipeline to be configured.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search query |
| `top_k` | int | No | Number of results to return |

### rag_ingest

Ingests a document into the RAG pipeline attached to the agent's context. Requires a RAG pipeline to be configured.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `document` | string | Yes | Document content to ingest |
| `metadata` | object | No | Document metadata |

## Security Considerations

- **`http_request`** blocks requests to localhost (`127.0.0.1`, `0.0.0.0`, `::1`) by default. Set `allow_localhost: true` in config to override.
- **`read_file` / `write_file`** support `allowed_paths` restrictions to limit filesystem access to specific directories.
- **`sql_query`** defaults to `read_only: true`, blocking all write and DDL statements.
- **`send_email`** uses `asyncio.to_thread()` for non-blocking SMTP operations.
- Secrets can be injected via `config` fields with `${ENV_VAR}` substitution or through `context.secrets` at runtime.

## Creating Custom Tools

Extend `BuiltinTool` to create your own tools:

```python
from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult

class MyTool(BuiltinTool):
    name = "my_tool"
    description = "Does something useful"
    parameters = {
        "type": "object",
        "properties": {"input": {"type": "string"}},
        "required": ["input"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True, data={"output": arguments["input"]})
```

Custom tools follow the same `async def execute()` contract as all built-in tools. Define `name`, `description`, and `parameters` (JSON Schema) as class attributes, then implement `execute()` to return a `ToolResult`.
