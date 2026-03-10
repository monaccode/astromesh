---
title: Multi-agent Composition
description: Using agents as tools, context transforms, and multi-agent orchestration patterns
---

Astromesh lets you compose agents into multi-agent systems where one agent can invoke another as a tool. A supervisor agent can delegate sub-tasks to specialist agents, a swarm of agents can hand off conversations to each other, and any agent can call another agent the same way it would call any other tool.

This page covers the agent-as-tool mechanism, context transforms for reshaping data between agents, and how the Supervisor and Swarm orchestration patterns leverage these capabilities.

## Agent-as-Tool

An agent registered as a tool appears in the parent agent's tool schema like any other function. When the LLM decides to call it, the ToolRegistry invokes the target agent's full execution pipeline -- memory, guardrails, orchestration, and all.

### Basic Configuration

In the parent agent's YAML, add a tool entry with `type: agent`:

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: sales-manager
  version: "1.0.0"

spec:
  identity:
    description: "Manages the sales pipeline by delegating to specialist agents"

  model:
    primary:
      provider: openai
      model: "gpt-4o"

  orchestration:
    pattern: react
    max_iterations: 15

  tools:
    - name: qualify-lead
      type: agent
      agent: sales-qualifier
      description: "Qualify a sales lead using BANT methodology"

    - name: draft-proposal
      type: agent
      agent: proposal-writer
      description: "Draft a sales proposal for a qualified lead"

    - name: web_search
      type: builtin
      config:
        provider: tavily
```

The `agent` field references the `metadata.name` of the target agent, which must be defined in its own `*.agent.yaml` file in the same `config/agents/` directory.

### Agent Tool Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | Yes | -- | Tool name as seen by the LLM |
| `type` | Yes | -- | Must be `agent` |
| `agent` | Yes | -- | `metadata.name` of the target agent |
| `description` | No | `"Invoke agent '<name>'"` | Description shown to the LLM in the tool schema |
| `parameters` | No | `{query: string}` | Custom JSON Schema for the tool's parameters |
| `context_transform` | No | -- | Jinja2 template to reshape data before passing to the target agent |
| `rate_limit` | No | -- | Per-tool rate limit (`max_calls`, `window_seconds`) |

### Default Parameters

When no custom `parameters` are specified, the agent tool exposes a single `query` parameter:

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "The query or task to send to the agent"
    }
  },
  "required": ["query"]
}
```

You can override this with a custom schema when the target agent expects structured input:

```yaml
tools:
  - name: analyze-financials
    type: agent
    agent: financial-analyst
    description: "Analyze financial data for a company"
    parameters:
      type: object
      properties:
        query:
          type: string
          description: "The analysis question"
        company:
          type: string
          description: "Company ticker symbol"
        fiscal_year:
          type: integer
          description: "Fiscal year to analyze"
      required: ["query", "company"]
```

---

## Context Transforms

Context transforms let you reshape data between agents using Jinja2 templates. This is useful when the parent agent collects information in one shape and the target agent expects it in another.

### How It Works

When a context transform is defined, the ToolRegistry:

1. Takes the arguments the LLM passed to the tool call
2. Wraps them in a `_DotDict` (enabling dot-notation access like `data.company` instead of `data["company"]`)
3. Renders the Jinja2 template with the arguments available as `data`
4. Parses the rendered JSON and passes it as the `context` parameter to the target agent's `run()` method

The transformed context is then available in the target agent's Jinja2 system prompt template.

### Syntax

The `context_transform` value is a Jinja2 expression that produces a JSON object. Arguments from the LLM's tool call are available under the `data` variable:

```yaml
tools:
  - name: qualify-lead
    type: agent
    agent: sales-qualifier
    context_transform: '{"company": "{{ data.company }}", "budget": "{{ data.budget }}"}'
```

You can use any Jinja2 features -- conditionals, filters, defaults:

```yaml
context_transform: >
  {
    "company": "{{ data.company | default('Unknown') }}",
    "priority": "{% if data.deal_size|int > 100000 %}high{% else %}normal{% endif %}"
  }
```

### Example: Sales Pipeline

Consider a sales manager agent that delegates lead qualification to a specialist:

**Parent agent (sales-manager.agent.yaml):**

```yaml
spec:
  tools:
    - name: qualify-lead
      type: agent
      agent: sales-qualifier
      description: "Qualify a lead. Provide company name, contact, and deal size."
      context_transform: >
        {
          "company": "{{ data.company }}",
          "contact_name": "{{ data.contact }}",
          "estimated_value": "{{ data.deal_size }}"
        }
```

**Target agent (sales-qualifier.agent.yaml):**

```yaml
spec:
  prompts:
    system: |
      You are a sales lead qualifier using BANT methodology.
      {% if company %}Company: {{ company }}{% endif %}
      {% if contact_name %}Contact: {{ contact_name }}{% endif %}
      {% if estimated_value %}Deal value: ${{ estimated_value }}{% endif %}

      Evaluate Budget, Authority, Need, and Timeline.
```

When the sales manager's LLM calls `qualify-lead` with arguments `{"query": "Qualify this lead", "company": "Acme Corp", "contact": "Jane Doe", "deal_size": "50000"}`, the context transform produces `{"company": "Acme Corp", "contact_name": "Jane Doe", "estimated_value": "50000"}`, which is injected into the qualifier's prompt template.

---

## Nested Tracing

When an agent calls another agent as a tool, both agents share the same trace tree. This gives you end-to-end visibility into multi-agent workflows.

### How It Works

The parent agent's execution context includes a `trace_id`. When the ToolRegistry executes an agent tool, it passes the `parent_trace_id` to the child agent's `run()` method. The child agent sets its tracing context's `trace_id` to the parent's, so all spans appear in a single trace.

```
Trace: abc-123
├── agent.run (sales-manager)
│   ├── memory_build
│   ├── prompt_render
│   ├── orchestration (react)
│   │   ├── llm.complete
│   │   ├── tool.call (qualify-lead)        ← agent tool invocation
│   │   │   └── agent.run (sales-qualifier) ← child agent's full pipeline
│   │   │       ├── memory_build
│   │   │       ├── prompt_render
│   │   │       ├── orchestration (react)
│   │   │       │   ├── llm.complete
│   │   │       │   └── llm.complete
│   │   │       └── memory_persist
│   │   ├── llm.complete
│   │   └── tool.call (draft-proposal)
│   │       └── agent.run (proposal-writer)
│   │           └── ...
│   └── memory_persist
```

Every span in the child agent's pipeline is nested under the parent's `tool.call` span, making it straightforward to trace latency, token usage, and errors across agent boundaries.

---

## Circular Reference Detection

Astromesh prevents infinite loops by detecting circular agent references at bootstrap time. Before any agents are instantiated, `AgentRuntime.bootstrap()` builds a dependency graph from all agent YAML files and runs a depth-first search (DFS) for cycles.

### What Gets Checked

The detection builds an adjacency list where each agent points to the agents it references via `type: agent` tools. If the DFS finds a back-edge (a node that is currently being visited), it raises a `ValueError` with the full cycle path.

```
Example cycle:

  agent-a → agent-b → agent-c → agent-a
                                  ↑ cycle!

Error: "Circular agent reference detected: agent-a -> agent-b -> agent-c -> agent-a"
```

### When It Runs

Circular reference detection runs once during `AgentRuntime.bootstrap()`, before any agents are created. If a cycle is detected, bootstrap fails immediately with a clear error message. This is a fail-fast safety check -- you will see the error in your logs as soon as the runtime starts.

### Allowed Topologies

Any directed acyclic graph (DAG) is valid:

```
Valid:                          Invalid:
  A → B                          A → B
  A → C                          B → C
  B → D                          C → A  (cycle!)
  C → D  (diamond, OK)
```

Multiple agents can reference the same target agent (diamond pattern). An agent can be both a standalone agent and a tool for other agents.

---

## Supervisor Pattern

The Supervisor pattern uses a central coordinating agent that decomposes tasks and delegates sub-tasks to worker agents. Workers are invoked via the agent-as-tool mechanism.

### Configuration

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: project-manager

spec:
  orchestration:
    pattern: supervisor
    max_iterations: 10

  tools:
    - name: researcher
      type: agent
      agent: research-agent
      description: "Research a topic and return findings"

    - name: writer
      type: agent
      agent: writing-agent
      description: "Write content based on research findings"

    - name: reviewer
      type: agent
      agent: review-agent
      description: "Review content for accuracy and quality"
```

### How It Works

1. The supervisor LLM receives the task and the list of available workers
2. It decides which worker to delegate to by returning JSON: `{"delegate": "researcher", "task": "Research the history of..."}`
3. The Supervisor pattern calls `tool_fn(worker_name, {"query": task})`, which routes through the ToolRegistry and invokes the target agent
4. The worker's result is added to the supervisor's context as an observation
5. The supervisor decides the next action -- delegate to another worker, or return a final answer: `{"final_answer": "..."}`
6. This loop continues until a final answer is produced or `max_iterations` is reached

```
┌─────────────────────────────────────────────┐
│              Supervisor Agent                │
│                                             │
│  "Research X, then write a report"          │
│       │                                     │
│       ├── delegate → researcher             │
│       │   └── returns findings              │
│       │                                     │
│       ├── delegate → writer                 │
│       │   └── returns draft                 │
│       │                                     │
│       ├── delegate → reviewer               │
│       │   └── returns feedback              │
│       │                                     │
│       └── final_answer → compiled report    │
└─────────────────────────────────────────────┘
```

### Worker Agents

Worker agents are standard Astromesh agents with their own YAML definitions. They can use any orchestration pattern, have their own tools, memory, and guardrails. The only requirement is that they exist in `config/agents/` and are referenced by name.

---

## Swarm Pattern

The Swarm pattern enables peer-to-peer agent collaboration where agents hand off conversations to each other based on context, without a central coordinator.

### Configuration

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: customer-support

spec:
  orchestration:
    pattern: swarm
    max_iterations: 10

  tools:
    - name: billing-agent
      type: agent
      agent: billing-specialist
      description: "Handle billing and payment questions"

    - name: technical-agent
      type: agent
      agent: tech-support
      description: "Handle technical issues and troubleshooting"

    - name: escalation-agent
      type: agent
      agent: human-escalation
      description: "Escalate to a human agent"
```

### How It Works

1. The initial agent receives the user's query
2. The agent either responds directly or hands off to another agent by returning JSON: `{"handoff": "billing-agent", "context": "Customer wants a refund for..."}`
3. On handoff, the Swarm pattern invokes the target agent via `tool_fn` and switches the current agent identity
4. The new agent continues the conversation, and can hand off again if needed
5. When an agent produces a direct response (no handoff, no tool call), the conversation ends

```
┌──────────────┐     handoff     ┌──────────────────┐
│  customer-   │ ──────────────▶ │  billing-        │
│  support     │                 │  specialist      │
└──────────────┘                 └────────┬─────────┘
                                          │ handoff
                                          ▼
                                 ┌──────────────────┐
                                 │  human-           │
                                 │  escalation       │
                                 └──────────────────┘
```

### Swarm vs. Supervisor

| Aspect | Supervisor | Swarm |
|--------|-----------|-------|
| **Coordination** | Central supervisor decomposes and delegates | Peer-to-peer, agents decide independently |
| **Control flow** | Supervisor always gets results back | Control transfers fully to the next agent |
| **Best for** | Complex tasks requiring planning and synthesis | Routing-style workflows (support triage, handoffs) |
| **Final response** | Supervisor synthesizes from all worker results | Whichever agent responds last |

---

## Real-World Example: Customer Support Pipeline

Here is a complete multi-agent setup for a customer support system:

**Triage agent (triage.agent.yaml):**

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: triage
  version: "1.0.0"

spec:
  identity:
    description: "Routes customer queries to the right specialist"

  model:
    primary:
      provider: openai
      model: "gpt-4o-mini"

  orchestration:
    pattern: swarm
    max_iterations: 5

  prompts:
    system: |
      You are a customer support triage agent. Analyze the customer's
      question and either answer simple questions directly or hand off
      to the appropriate specialist.

  tools:
    - name: billing-specialist
      type: agent
      agent: billing
      description: "Handles billing, invoices, refunds, and payment issues"

    - name: technical-specialist
      type: agent
      agent: tech-support
      description: "Handles technical issues, bugs, and troubleshooting"
      context_transform: '{"issue_category": "{{ data.query | truncate(100) }}"}'

    - name: knowledge_base
      type: builtin
      config:
        provider: tavily
```

**Billing agent (billing.agent.yaml):**

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: billing
  version: "1.0.0"

spec:
  identity:
    description: "Specialist for billing and payment queries"

  model:
    primary:
      provider: openai
      model: "gpt-4o"

  orchestration:
    pattern: react
    max_iterations: 8

  prompts:
    system: |
      You are a billing specialist. Help customers with invoices,
      refunds, payment methods, and subscription changes.

  tools:
    - name: sql_query
      type: builtin
      config:
        connection_string: "postgresql://billing_ro@db:5432/billing"
        read_only: true

  guardrails:
    output:
      - type: pii_detection
        action: redact
```

This setup routes customers to the right agent automatically. The triage agent uses the Swarm pattern to hand off, while each specialist uses ReAct with its own tools and guardrails.
