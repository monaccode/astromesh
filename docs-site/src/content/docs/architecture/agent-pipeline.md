---
title: Agent Execution Pipeline
description: Step-by-step walkthrough of how a request flows through an agent
---

When a request reaches Astromesh, it passes through a 12-step pipeline before a response is returned. This page traces every step in detail -- what happens, which module handles it, and what data flows between stages.

For the architectural context behind this pipeline, see [Four-Layer Design](/astromesh/architecture/four-layer-design/). For the high-level system map, see [Architecture Overview](/astromesh/architecture/overview/).

## Pipeline Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Agent Execution Pipeline                      │
│                                                                      │
│  1. Request Arrives                                                  │
│     │                                                                │
│  2. AgentRuntime.run()                                               │
│     │                                                                │
│  3. Input Guardrails          ←── block / redact / pass              │
│     │                                                                │
│  4. Memory Context            ←── conversational + semantic +        │
│     │                              episodic                          │
│  5. Prompt Rendering          ←── Jinja2 system prompt               │
│     │                                                                │
│  6. Tool Schema Generation    ←── JSON schemas for function calling  │
│     │                                                                │
│  7. Orchestration Pattern     ←── reasoning loop (e.g., ReAct)       │
│     │   ┌─────────────────────────────────────┐                      │
│     │   │  8. Model Routing   → LLM call      │                      │
│     │   │  9. Tool Execution  → if requested   │ ← iterates          │
│     │   └─────────────────────────────────────┘                      │
│     │                                                                │
│ 10. Output Guardrails         ←── filter / redact / block            │
│     │                                                                │
│ 11. Memory Persistence        ←── save user + assistant turns        │
│     │                                                                │
│ 12. Response                  ←── JSON returned to caller            │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Step 1: Request Arrives

**Module:** `astromesh/api/routes/agents.py` or `astromesh/api/ws.py`

A request enters Astromesh through one of two interfaces:

### HTTP POST

```bash
curl -X POST http://localhost:8000/v1/agents/support-agent/run \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I reset my password?", "session_id": "session-42"}'
```

The FastAPI route handler at `POST /v1/agents/{name}/run` receives the request, validates the JSON body (must contain `query` and `session_id`), and extracts the agent name from the URL path.

### WebSocket

```
ws://localhost:8000/v1/ws/agent/support-agent
```

The WebSocket handler at `/v1/ws/agent/{agent_name}` accepts the connection, registers it with the `ConnectionManager`, and waits for JSON messages. Each message triggers the same pipeline, but responses are streamed back token-by-token instead of returned as a single JSON response.

### Channel Adapter (WhatsApp)

For channel-based requests, the flow is slightly different. The WhatsApp adapter at `POST /v1/channels/whatsapp/webhook` receives Meta's webhook payload, validates the HMAC signature, extracts the message text, and spawns a **background task** to run the agent. This ensures the webhook responds to Meta within the required 5-second window. The agent's response is sent back to the user asynchronously via the WhatsApp Business Cloud API.

---

## Step 2: AgentRuntime.run()

**Module:** `astromesh/runtime/engine.py`

The route handler calls `runtime.run(agent_name, query, session_id)`. The Runtime Engine:

1. **Looks up the agent** by name in its internal dictionary of bootstrapped agents. If the agent does not exist, it returns a 404 error.
2. **Creates an execution context** containing the query, session ID, and any additional metadata (e.g., channel source, user identity).
3. **Delegates to `Agent.run()`**, which begins the execution pipeline.

```python
# Simplified flow
async def run(self, agent_name: str, query: str, session_id: str):
    agent = self.agents.get(agent_name)
    if not agent:
        raise AgentNotFoundError(agent_name)
    return await agent.run(query, session_id)
```

---

## Step 3: Input Guardrails

**Module:** `astromesh/core/guardrails.py`

Before the agent processes the query, input guardrails run in the order defined in the agent's YAML configuration. Each guardrail examines the incoming query and takes one of three actions:

| Action | Effect |
|--------|--------|
| **Pass** | The query continues unchanged |
| **Redact** | The query is modified (e.g., PII is replaced with placeholders) and continues |
| **Block** | The pipeline stops immediately and an error response is returned |

### Input guardrail types

**PII Detection** scans the query for patterns matching emails, phone numbers, SSNs, and credit card numbers. In input mode, it can either redact the PII (replacing it with `[EMAIL]`, `[PHONE]`, etc.) or block the request entirely, depending on configuration.

**Topic Filter** checks the query against a list of forbidden topics. If the query matches a forbidden topic (via keyword or pattern matching), the request is blocked with a configurable rejection message.

**Max Length** checks the character count of the query. If it exceeds the configured maximum, the request is blocked. This prevents abuse and ensures the query fits within reasonable bounds before prompt construction.

Example guardrails configuration in agent YAML:

```yaml
spec:
  guardrails:
    input:
      - type: pii_detection
        action: redact
      - type: topic_filter
        forbidden_topics: ["violence", "illegal_activity"]
        action: block
      - type: max_length
        max_characters: 5000
```

---

## Step 4: Memory Context

**Module:** `astromesh/core/memory.py`

After input guardrails pass, the Memory Manager assembles context from all configured memory types by calling `build_context(agent_name, session_id, query)`.

### What happens during context building

1. **Conversational memory** -- The manager retrieves recent chat history for the given session. The configured memory strategy determines how much history is included:
   - `sliding_window`: Returns the last N turns
   - `summary`: Returns a compressed summary of older turns plus the last few turns verbatim
   - `token_budget`: Returns as many recent turns as fit within the configured token limit

2. **Semantic memory** -- If semantic memory is configured, the query is embedded and a vector similarity search is performed against the semantic store. The top-K most relevant results are returned. This gives the agent access to long-term knowledge that may be relevant to the current query.

3. **Episodic memory** -- If episodic memory is configured, recent events (tool calls, significant outcomes, user feedback) for the session are retrieved. This gives the agent awareness of what has happened in the broader conversation context.

The output is a structured context object containing all three memory types, ready to be injected into the prompt template.

```
Memory Context Output:
├── conversation_history: [Message, Message, ...]
├── semantic_results: [{"content": "...", "score": 0.92}, ...]
└── episodic_events: [{"event": "tool_call", "tool": "search", ...}, ...]
```

---

## Step 5: Prompt Rendering

**Module:** `astromesh/core/prompt_engine.py`

The Prompt Engine takes the agent's system prompt template (a Jinja2 string from the `prompts.system` field in the agent YAML) and renders it with the assembled context variables.

### Template variables

The following variables are available in the system prompt template:

| Variable | Source | Content |
|----------|--------|---------|
| `agent_name` | Agent YAML `metadata.name` | The agent's name |
| `description` | Agent YAML `spec.identity.description` | The agent's description |
| `conversation_history` | Memory Manager | List of previous messages |
| `semantic_context` | Memory Manager | Relevant knowledge from vector search |
| `episodic_events` | Memory Manager | Recent events and tool call history |
| `current_date` | System | Current date/time string |
| Custom variables | Agent YAML `prompts.variables` | Any additional configured variables |

### SilentUndefined

The Prompt Engine uses Jinja2's `SilentUndefined` mode. This means if a variable is referenced in the template but not available (e.g., no semantic memory is configured), it renders as an empty string rather than raising an error. This allows a single prompt template to work correctly whether or not optional features like semantic memory are enabled.

### Rendered output

The rendered system prompt becomes the `system` message in the LLM conversation. It is combined with the conversation history to form the complete message array sent to the LLM provider.

---

## Step 6: Tool Schema Generation

**Module:** `astromesh/core/tools.py`

Before entering the orchestration loop, the Tool Registry generates JSON schemas for all tools available to this agent. These schemas follow the OpenAI function calling format and are passed to the LLM provider so it can decide when and how to call tools.

```json
{
  "type": "function",
  "function": {
    "name": "search_knowledge_base",
    "description": "Search the knowledge base for relevant information",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "The search query"
        },
        "top_k": {
          "type": "integer",
          "description": "Number of results to return",
          "default": 5
        }
      },
      "required": ["query"]
    }
  }
}
```

The registry filters tools based on the agent's permissions -- each agent only sees the tools it is authorized to use, as specified in its YAML configuration.

---

## Step 7: Orchestration Pattern

**Module:** `astromesh/orchestration/patterns.py`, `supervisor.py`, `swarm.py`

The orchestration pattern controls the reasoning loop -- how the agent thinks, acts, and decides when it is done. The pattern receives two callable functions (`model_fn` for LLM calls and `tool_fn` for tool execution) and iterates until it produces a final answer or hits the configured `max_iterations` limit.

### ReAct Example (most common pattern)

The ReAct (Reasoning + Acting) pattern is the most widely used. Here is how a single iteration works:

```
Iteration 1:
┌─────────────────────────────────────────────────┐
│ THINK: LLM receives messages + tool schemas     │
│        LLM decides: "I need to search the KB"   │
│                                                  │
│ ACT:   LLM returns tool_call:                    │
│        search_knowledge_base(query="password     │
│        reset procedure")                         │
│                                                  │
│ OBSERVE: Tool executes, returns results:         │
│          "To reset your password, go to..."      │
│          Result is added to message history       │
└─────────────────────────────────────────────────┘

Iteration 2:
┌─────────────────────────────────────────────────┐
│ THINK: LLM receives updated messages (with       │
│        tool results)                             │
│        LLM decides: "I have enough info"         │
│                                                  │
│ ACT:   LLM returns a text response (no tool      │
│        call) → this is the final answer          │
└─────────────────────────────────────────────────┘
```

### Other patterns

**PlanAndExecute** first asks the LLM to create a numbered plan, then executes each step sequentially, calling tools as needed at each step.

**ParallelFanOut** sends the query to multiple providers simultaneously and merges the results. Useful for getting diverse perspectives or ensemble-style responses.

**Pipeline** chains multiple processing steps, where each step's output becomes the next step's input. Useful for data transformation workflows.

**Supervisor** uses a supervisor agent that decomposes the task and delegates sub-tasks to specialized worker agents.

**Swarm** allows multiple agents to hand off conversations to each other based on the conversation context, without a central coordinator.

---

## Step 8: Model Routing

**Module:** `astromesh/core/model_router.py`

Within each orchestration iteration, when the pattern needs an LLM completion, it calls `model_fn()`, which delegates to the Model Router.

The Model Router performs the following sequence:

1. **Rank providers** using the configured routing strategy (e.g., `cost_optimized` sorts by `estimated_cost()`, `latency_optimized` sorts by `avg_latency_ms`).

2. **Check circuit breaker** for the top-ranked provider. If the circuit is open (the provider has failed 3+ times recently and the 60-second cooldown has not elapsed), skip to the next provider.

3. **Call the provider** via `provider.complete()` (or `provider.stream()` for WebSocket). Pass the rendered messages and tool schemas.

4. **Handle failure** -- If the provider call fails (network error, timeout, API error), increment the failure counter, and try the next provider in the ranked list.

5. **Update metrics** -- On success, update the provider's latency moving average and reset its failure counter. Record the token usage for cost tracking.

```
model_fn(messages, tools)
    │
    ▼
ModelRouter.route()
    │
    ├── Strategy ranks: [ollama, openai, vllm]
    │
    ├── Try ollama ──► circuit OPEN (3 failures) ──► skip
    ├── Try openai ──► circuit CLOSED ──► call provider
    │   └── Success! Update latency, reset failures
    │
    └── Return CompletionResult
```

If all providers fail, the router raises an error that propagates back through the pipeline.

---

## Step 9: Tool Execution

**Module:** `astromesh/core/tools.py`

If the LLM's response includes a tool call (a structured request to invoke a specific function with arguments), the orchestration pattern intercepts it and delegates to the Tool Registry.

The Tool Registry:

1. **Validates the tool call** -- Checks that the tool exists, the agent has permission to use it, and the rate limit has not been exceeded.
2. **Deserializes arguments** -- Parses the JSON arguments from the LLM's tool call.
3. **Executes the tool** based on its type:
   - **Internal**: Calls the registered Python async function directly
   - **MCP**: Sends a JSON-RPC request to the MCP server
   - **Webhook**: Makes an HTTP request to the configured endpoint
   - **RAG**: Runs a query through the RAG pipeline
4. **Returns the result** -- The tool's output is formatted as a tool result message and added to the conversation, so the LLM can see it in the next iteration.

```python
# Simplified tool execution
async def execute(self, tool_name: str, arguments: dict, agent_name: str):
    tool = self.tools[tool_name]

    # Permission check
    if tool_name not in self.agent_permissions[agent_name]:
        raise ToolPermissionError(tool_name, agent_name)

    # Rate limit check
    if self.is_rate_limited(tool_name, agent_name):
        raise ToolRateLimitError(tool_name)

    # Execute based on type
    match tool.type:
        case "internal":
            return await tool.function(**arguments)
        case "mcp":
            return await self.mcp_client.call_tool(tool.server, tool_name, arguments)
        case "webhook":
            return await self.http_client.post(tool.endpoint, json=arguments)
        case "rag":
            return await self.rag_pipeline.query(arguments["query"])
```

After tool execution, the result is appended to the message history and the orchestration pattern loops back to Step 8 for the next iteration.

---

## Step 10: Output Guardrails

**Module:** `astromesh/core/guardrails.py`

Once the orchestration pattern produces a final answer, output guardrails run on the response before it is returned to the caller.

### Output guardrail types

**Content Filter** checks the response for forbidden keywords or patterns. If found, the response is either redacted (offending content replaced) or blocked (a generic safe response is returned instead).

**Cost Limit** checks whether the total tokens used in this turn exceed the configured per-turn limit. If exceeded, the response is truncated or an error is returned. This prevents runaway token usage from expensive orchestration loops.

**PII Detection** (output mode) scans the response for PII patterns and redacts them before returning to the caller. This catches cases where the LLM generates PII in its response (e.g., generating fake but realistic-looking credit card numbers in examples).

```yaml
spec:
  guardrails:
    output:
      - type: content_filter
        forbidden_keywords: ["internal_only", "classified"]
        action: redact
      - type: cost_limit
        max_tokens_per_turn: 4000
      - type: pii_detection
        action: redact
```

---

## Step 11: Memory Persistence

**Module:** `astromesh/core/memory.py`

After output guardrails pass, the Memory Manager persists the conversation turn. Two calls are made:

1. **`persist_turn(user_message)`** -- Stores the user's original query (after input guardrail redaction, if any) as a conversation turn.
2. **`persist_turn(assistant_message)`** -- Stores the agent's final response as a conversation turn.

Both turns are written to the configured conversational memory backend (Redis, PostgreSQL, or SQLite) and associated with the session ID.

If **episodic memory** is configured, significant events from the execution are also recorded:
- Tool calls made (tool name, arguments, result summary)
- Provider used and latency
- Guardrail actions taken (redactions, blocks)
- Total token usage and estimated cost

If **semantic memory** is configured and the agent has auto-indexing enabled, the assistant's response may be embedded and stored in the vector store for future retrieval.

---

## Step 12: Response

**Module:** `astromesh/api/routes/agents.py` or `astromesh/api/ws.py`

The final response is returned to the caller in the format appropriate for the transport:

### HTTP Response

```json
{
  "response": "To reset your password, go to Settings > Security > Reset Password...",
  "agent": "support-agent",
  "session_id": "session-42",
  "metadata": {
    "provider": "ollama",
    "model": "llama3.1:8b",
    "tokens_used": 342,
    "latency_ms": 1250,
    "tools_called": ["search_knowledge_base"]
  }
}
```

### WebSocket Response

For WebSocket connections, the response was already streamed token-by-token during Step 8. The final message includes the complete response and a `done: true` flag.

### Channel Response

For channel-based requests (e.g., WhatsApp), the agent's response is sent back to the user through the channel's API (e.g., WhatsApp Business Cloud API) by the background task spawned in Step 1.

---

## Configuration Loading Flow

Before the pipeline can run, configuration files must be loaded and parsed. This happens once at startup during `AgentRuntime.bootstrap()`.

```
config/
├── agents/*.agent.yaml    ──► AgentRuntime.bootstrap()
│                               ├── Parse YAML
│                               ├── Validate apiVersion + kind
│                               ├── Build ModelRouter
│                               │   ├── Instantiate primary provider
│                               │   ├── Instantiate fallback providers
│                               │   └── Set routing strategy
│                               ├── Build MemoryManager
│                               │   ├── Select conversational backend
│                               │   ├── Select semantic backend (optional)
│                               │   ├── Select episodic backend (optional)
│                               │   └── Set memory strategy
│                               ├── Build ToolRegistry
│                               │   ├── Register internal tools
│                               │   ├── Connect to MCP servers
│                               │   ├── Register webhook tools
│                               │   └── Register RAG tools
│                               ├── Select OrchestrationPattern
│                               ├── Build PromptEngine
│                               │   └── Register system prompt template
│                               ├── Build GuardrailsEngine
│                               │   ├── Configure input guardrails
│                               │   └── Configure output guardrails
│                               └── Create Agent instance
│
├── providers.yaml         ──► Provider registration (endpoints, credentials)
├── rag/*.rag.yaml         ──► RAG pipeline configuration
├── channels.yaml          ──► Channel adapter configuration
└── runtime.yaml           ──► API and runtime defaults (port, log level, etc.)
```

---

## Data Flow Diagram

This diagram maps each pipeline step to the module that handles it:

```
Step                        Module                          Layer
────                        ──────                          ─────
1.  Request Arrives         api/routes/agents.py            API Layer
                            api/ws.py
                            channels/whatsapp.py

2.  AgentRuntime.run()      runtime/engine.py               Runtime Engine

3.  Input Guardrails        core/guardrails.py              Core Services

4.  Memory Context          core/memory.py                  Core Services
                            memory/backends/*               Infrastructure
                            memory/strategies/*             Infrastructure

5.  Prompt Rendering        core/prompt_engine.py           Core Services

6.  Tool Schema Gen         core/tools.py                   Core Services

7.  Orchestration           orchestration/patterns.py       Infrastructure
                            orchestration/supervisor.py
                            orchestration/swarm.py

8.  Model Routing           core/model_router.py            Core Services
                            providers/*                     Infrastructure

9.  Tool Execution          core/tools.py                   Core Services
                            mcp/client.py                   Infrastructure
                            rag/pipeline.py                 Infrastructure

10. Output Guardrails       core/guardrails.py              Core Services

11. Memory Persistence      core/memory.py                  Core Services
                            memory/backends/*               Infrastructure

12. Response                api/routes/agents.py            API Layer
                            api/ws.py
```

Each step cleanly separates the orchestration logic (Core Services) from the concrete implementations (Infrastructure), maintaining the strict layer boundaries described in [Four-Layer Design](/astromesh/architecture/four-layer-design/).
