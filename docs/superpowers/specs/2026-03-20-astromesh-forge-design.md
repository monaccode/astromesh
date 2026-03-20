# Astromesh Forge — Design Spec v1

## Goal

**Astromesh Forge** is a visual agent builder that replaces and evolves `astromesh-cloud`. It is a lightweight SPA (Vite + React) that connects directly to an Astromesh node's API to create, edit, and deploy agents — via an improved wizard and a drag-and-drop canvas with two zoom levels (macro: agent orchestration, micro: internal pipeline). Forge includes a gallery of pre-built business-case templates and supports three deploy targets: local, remote node, and Nexus (future managed cloud).

## Target User

Non-technical and semi-technical users who need to build and deploy AI agents without editing YAML files or managing infrastructure. Also useful for technical users who prefer a visual approach to designing complex multi-agent orchestrations.

## What Forge IS

- Improved step-by-step wizard for agent creation (evolution of existing Studio wizard)
- Visual canvas with two levels: macro (orchestration between agents) and micro (internal pipeline of a single agent)
- Dashboard for listing agents with status and CRUD + deploy/pause actions
- Templates gallery with pre-built agents for common business use cases
- Deploy client to 3 targets: local runtime, remote Astromesh node, Nexus (future)

## What Forge is NOT

- No monitoring, metrics, logs, or traces — that is **Cortex** (separate paid product)
- No backend of its own — communicates directly with the Astromesh node API
- No auth/tenancy — authentication is handled by the node or Nexus

## Relationship to Astromesh Cloud

Forge replaces `astromesh-cloud`:

- `astromesh-cloud/web/` → refactored into `astromesh-forge/` (SPA, no Next.js)
- `astromesh-cloud/api/` → **deprecated**. Its agent CRUD/deploy functionality already exists in the core API (`/v1/agents`). Cloud-specific features (orgs, billing, tenancy) will migrate to **Nexus** in the future.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Astromesh Forge                          │
│                                                             │
│  ┌──────────────────────┐         ┌──────────────────────┐  │
│  │   Forge SPA          │──HTTP──▶│   Astromesh Node     │  │
│  │   (Vite + React)     │         │   API (/v1/*)        │  │
│  │                      │◀─JSON───│                      │  │
│  └──────────────────────┘         └──────────────────────┘  │
│                                                             │
│  No backend. No database. Pure client.                      │
└─────────────────────────────────────────────────────────────┘
```

**Key principle:** Forge is a client application. All state lives in the Astromesh node. Forge reads and writes via the existing `/v1/*` API endpoints.

---

## Tech Stack

### Frontend

| Technology | Purpose |
|-----------|---------|
| **Vite + React + TypeScript** | SPA framework — compiles to static files for easy embedding |
| **React Flow** | Canvas for node-based visual editing |
| **dnd-kit** | Drag & drop for wizard (reorder tools, guardrails, etc.) |
| **Tailwind CSS** | Styling, consistent with Astromesh ecosystem |
| **Zustand** | Lightweight global state (agent in editor, node connection, agent list) |
| **React Router** | SPA navigation |

### Why Vite instead of Next.js

Next.js requires a Node server for SSR, which complicates embedding in FastAPI. Vite compiles to pure static files that can be served from any HTTP server — including FastAPI's `StaticFiles` mount.

---

## Project Structure

```
astromesh-forge/
├── public/
├── src/
│   ├── api/              # HTTP client to Astromesh node (/v1/*)
│   ├── components/
│   │   ├── ui/           # Base components (buttons, inputs, cards)
│   │   ├── wizard/       # Step-by-step creation wizard
│   │   ├── canvas/       # Visual canvas (React Flow)
│   │   │   ├── nodes/    # Node types (agent, tool, guardrail, model, memory)
│   │   │   ├── edges/    # Connections between nodes
│   │   │   └── panels/   # Properties panel, toolbox sidebar
│   │   ├── dashboard/    # Agent list, status, actions
│   │   ├── templates/    # Templates gallery
│   │   └── deploy/       # Target selector + confirmation
│   ├── hooks/            # Custom hooks (useAgent, useNode, useCanvas)
│   ├── stores/           # Zustand stores
│   ├── types/            # TypeScript types (AgentConfig, NodeTypes, etc.)
│   ├── utils/            # Converters canvas↔YAML, validation
│   └── App.tsx
├── package.json
├── vite.config.ts
├── tailwind.config.ts
└── tsconfig.json
```

---

## Distribution

### Embedded mode (in the node)

- Forge compiles to static files (`dist/`) copied to `astromesh/static/forge/`
- FastAPI serves them via `StaticFiles` mount at `/forge`
- No URL configuration needed — uses relative paths (`/v1/agents`)
- Enabled/disabled via node config: `services.forge: true/false`

### Standalone mode

- `npx astromesh-forge` starts Vite preview server
- URL passed at startup: `npx astromesh-forge --node http://host:8000`
- Can also be built as static files and served from any HTTP server
- Node URL configurable via `VITE_ASTROMESH_URL` env var or in-app settings

### CORS

In standalone mode, the Astromesh node must allow CORS from Forge's origin. Configuration via `config/runtime.yaml`:

```yaml
cors_origins: ["http://localhost:5173"]
```

---

## API Communication

Forge talks to the Astromesh node API. Some endpoints already exist, others need to be implemented:

| Method | Endpoint | Purpose | Status |
|--------|----------|---------|--------|
| `GET` | `/v1/agents` | List agents | **Exists** |
| `POST` | `/v1/agents` | Create agent | **Exists** |
| `GET` | `/v1/agents/{name}` | Get agent detail | **Exists** |
| `PUT` | `/v1/agents/{name}` | Update agent | **New** |
| `DELETE` | `/v1/agents/{name}` | Delete agent | **Exists** |
| `POST` | `/v1/agents/{name}/deploy` | Deploy agent | **New** |
| `POST` | `/v1/agents/{name}/pause` | Pause agent | **New** |
| `GET` | `/v1/tools` | List available tools | **Exists** |
| `GET` | `/v1/system` | Health check | **Exists** |
| `GET` | `/v1/templates` | List templates | **New** |
| `GET` | `/v1/templates/{name}` | Template detail | **New** |

### New endpoints required on the core API

- `PUT /v1/agents/{name}` — Update an existing agent's configuration
- `POST /v1/agents/{name}/deploy` — Deploy a draft/paused agent to the runtime (loads into `_agents` dict, sets status to `deployed`)
- `POST /v1/agents/{name}/pause` — Pause a deployed agent (unloads from `_agents` dict, sets status to `paused`)
- `GET /v1/templates` — List available agent templates (reads from `config/templates/`)
- `GET /v1/templates/{name}` — Return detail of a specific template

---

## Wizard (Evolution of Existing)

The current Studio has a 5-step wizard. Forge evolves it to 7 steps with improved UX:

### Step 1 — Identity

- Agent name (auto-generated slug)
- Display name
- Description
- Avatar picker
- Tags/labels for organization

### Step 2 — Model

- Primary model: provider + model selector
- Fallback model (optional): drag to set priority
- Routing strategy selector (cost_optimized, latency_optimized, quality_first, round_robin)
- Provider parameters inline (temperature, top_p, max_tokens)

### Step 3 — Tools

- Left panel shows available tools from the node (fetched via `GET /v1/tools`)
- Drag & drop tools to the agent's tool list
- Inline configuration per tool (parameters, permissions)
- Tool types displayed: internal, MCP, webhook, RAG

### Step 4 — Orchestration

- Pattern selector with visual diagram explaining each:
  - **ReAct** — Think → Act → Observe loop
  - **Plan and Execute** — Plan steps first, then execute
  - **Parallel Fan-Out** — Split into parallel branches
  - **Pipeline** — Sequential processing chain
  - **Supervisor** — Coordinator delegates to workers
  - **Swarm** — Autonomous agents collaborating
- Max iterations and timeout configuration

### Step 5 — Settings

- **Memory:** backend selector + strategy + max_turns + TTL toggles per memory type (conversational, semantic, episodic)
- **Guardrails:** drag & drop guardrails from available list into input/output sections. Inline config per guardrail (type, action, thresholds)
- **Permissions:** allowed actions, filesystem, network constraints

### Step 6 — Prompts

- System prompt editor with Jinja2 syntax highlighting
- Available template variables shown as insertable chips
- Named template definitions (optional)
- Live preview of rendered prompt

### Step 7 — Review & Deploy

- Full YAML preview (collapsible)
- Target selector: Local / Remote Node / Nexus
- Dry-run test with inline chat
- Deploy button
- "Open in Canvas" button to switch to visual editor

### Wizard ↔ Canvas interop

- Both views operate on the same data model (`AgentConfig` as JSON)
- Editing in the wizard updates the canvas and vice versa
- The JSON model maps 1:1 to the agent YAML schema
- "Open in Canvas" button available at any wizard step

---

## Canvas Visual

The canvas is the core differentiator of Forge. It operates at two zoom levels on the same workspace.

### Macro View — Orchestration between agents

Each node is a complete agent (icon + name + status). Connections define the orchestration pattern:

```
┌──────────┐       ┌──────────┐
│ Supervisor│──────▶│ Researcher│
│  Agent    │       │  Agent    │
└──────────┘       └──────────┘
      │
      │            ┌──────────┐
      └───────────▶│ Writer   │
                   │  Agent    │
                   └──────────┘
```

- Drag agents from left sidebar panel (existing agents on the node, or create new)
- Connections define relationships: supervisor→worker, pipeline step, fan-out branch
- Orchestration pattern inferred from topology or selected explicitly
- **v1:** Multi-agent orchestration is defined by configuring agent-as-tool references (the existing `type: agent` tool in the YAML schema). The canvas visually represents these relationships. Each agent is deployed individually.
- **Future (v2):** First-class "workflow" concept (`kind: Workflow`) that groups agents into a deployable unit with its own lifecycle. Requires a new YAML schema and API endpoints — deferred to v2.

### Micro View — Internal pipeline (drill-down)

Double-click an agent node to expand its internal pipeline:

```
┌─────────────────────────────────────────────────┐
│ Sales Qualifier Agent                            │
│                                                  │
│ [Input Guardrails] → [Memory] → [Prompt Engine] │
│       ↓                              ↓           │
│ [PII Filter]      [System Prompt + Jinja2]       │
│ [Max Length]              ↓                       │
│                    [Model Router]                 │
│                     ↓        ↓                    │
│              [Primary]  [Fallback]                │
│                     ↓                             │
│              [Tool Calls]                         │
│              ↓    ↓    ↓                          │
│         [CRM] [Email] [Search]                    │
│                     ↓                             │
│          [Output Guardrails]                      │
│              ↓         ↓                          │
│        [Cost Limit] [Content Filter]              │
└─────────────────────────────────────────────────┘
```

- Each pipeline block is an editable node (click to open properties panel)
- Drag & drop to add/reorder guardrails, tools, memory backends
- Changes in micro view reflect in wizard and YAML

### Properties Panel (right sidebar)

Contextual form when selecting any node:

- **Tool node** → name, type (internal/mcp/webhook/rag), parameters, permissions
- **Model node** → provider, model, endpoint, parameters (temperature, top_p, max_tokens)
- **Guardrail node** → type, action (block/redact), specific configuration
- **Memory node** → backend, strategy, max_turns, TTL

### Toolbox (left sidebar)

Draggable categories:

- **Agents** — existing agents on the node
- **Tools** — registered tools on the node (internal, MCP, webhook, RAG)
- **Models** — available providers/models
- **Guardrails** — input and output types
- **Memory** — configured backends

---

## Templates Gallery (Pre-built Agents)

A gallery of agent templates organized by business use case, ready to customize and deploy.

### Access

- Main Forge screen: "Start from Template" button alongside "Create from Scratch"
- Also accessible from dashboard as quick action

### Template structure

Each template includes:

| Field | Description |
|-------|-------------|
| `name` | Template slug identifier |
| `display_name` | Human-readable name |
| `description` | What the agent does, business case it solves |
| `category` | Business category |
| `tags` | Searchable tags |
| `recommended_channels` | Best channels for this use case with integration notes |
| `variables` | Placeholders to customize (`{{company_name}}`, `{{brand_voice}}`, etc.) |
| `agent_config` | Complete agent YAML (model, tools, orchestration, guardrails, prompts) |

### Template file format

Templates are stored as `.template.yaml` in `config/templates/`:

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: sales-qualifier
  version: "1.0.0"
  category: sales
  tags: [leads, bant, qualification, crm]

template:
  display_name: "Sales Lead Qualifier"
  description: >
    Qualifies incoming sales leads using BANT methodology.
    Scores leads 1-10 and recommends next actions.
    Integrates with CRM for company lookup.
  recommended_channels:
    - channel: whatsapp
      reason: "Direct lead engagement via business messaging"
    - channel: web_chat
      reason: "Embed in landing pages for inbound qualification"
  variables:
    - key: company_name
      label: "Your company name"
      placeholder: "Acme Corp"
      required: true
    - key: product_name
      label: "Product or service you sell"
      placeholder: "Cloud hosting solutions"
      required: true
    - key: brand_voice
      label: "Tone of communication"
      placeholder: "Professional and consultative"
      default: "Professional and consultative"

  agent_config:
    # Full agent YAML spec — see individual template definitions below
```

### Template catalog

#### Sales

| Template | Recommended Channels | Description |
|----------|---------------------|-------------|
| **Sales Qualifier** | WhatsApp, Web Chat | Qualifies leads using BANT methodology. Scores 1-10, recommends next action. CRM integration for company lookup. |
| **Product Advisor** | WhatsApp, Telegram | Recommends products based on customer needs. Asks discovery questions, matches to catalog, generates comparisons. |

#### Customer Service

| Template | Recommended Channels | Description |
|----------|---------------------|-------------|
| **Support Agent** | WhatsApp, Telegram, Web Chat | Resolves FAQs using RAG-powered knowledge base. Escalates to human when confidence is low. Empathetic tone. |
| **Returns & Claims** | WhatsApp | Manages product returns and warranty claims. Collects order info, validates policy, generates return labels. |

#### Collections

| Template | Recommended Channels | Description |
|----------|---------------------|-------------|
| **Payment Reminder** | WhatsApp | Sends payment reminders with configurable escalation. Friendly first notice, firmer follow-ups. Negotiates payment plans. |
| **Debt Collector** | WhatsApp, Telegram | Structured debt follow-up. Generates payment commitments, tracks promises, escalates non-responsive accounts. |

#### Marketing

| Template | Recommended Channels | Description |
|----------|---------------------|-------------|
| **Campaign Bot** | Telegram, WhatsApp | Sends promotional campaigns, segments responses by interest, captures leads from engagement. |

#### Industry: Food & Beverage

| Template | Recommended Channels | Description |
|----------|---------------------|-------------|
| **Brand Chef** | WhatsApp, Instagram | Recommends recipes using the brand's products. Cooking tips, meal planning, ingredient substitutions. Personalized to user preferences. |
| **Nutritionist** | Web Chat | Nutritional information about products. Dietary recommendations, allergen alerts, healthy combinations. |

#### Industry: Automotive

| Template | Recommended Channels | Description |
|----------|---------------------|-------------|
| **Service Scheduler** | WhatsApp, Web Chat | Schedules workshop appointments. Reminds preventive maintenance based on mileage. Receives problem photos for pre-diagnosis. |
| **Parts Advisor** | WhatsApp | Checks parts availability, generates quotes, schedules installation appointments. Compatible parts lookup by vehicle model. |

#### Industry: Real Estate

| Template | Recommended Channels | Description |
|----------|---------------------|-------------|
| **Property Agent** | WhatsApp | Qualifies interested buyers/renters. Matches preferences to listings. Schedules property viewings. |

#### Industry: Education

| Template | Recommended Channels | Description |
|----------|---------------------|-------------|
| **Tutor Assistant** | Telegram, Web Chat | Homework help, concept explanations, practice exercises. Adapts to student level. |

#### Internal Operations

| Template | Recommended Channels | Description |
|----------|---------------------|-------------|
| **HR Assistant** | Slack, Web Chat | Answers HR questions (policies, vacation balance, benefits). Routes complex requests to HR team. |
| **Onboarding Buddy** | Slack | Guides new employees through first weeks. Checklist tracking, team introductions, tool setup help. |

### Template usage flow

```
Gallery → Browse/search by category → Select template → Preview (description + YAML + channels)
  → "Use Template" → Wizard opens pre-filled with template config
  → Customize variables (company name, tone, specifics)
  → Optionally edit tools, model, guardrails
  → Review → Deploy
```

### Template variable processing

Template variables (e.g., `{{company_name}}`, `{{brand_voice}}`) are resolved **client-side in Forge** before sending to the node API. The process:

1. Forge fetches the template from `GET /v1/templates/{name}`
2. User fills in the variables in the wizard UI
3. Forge performs string substitution on the `agent_config` JSON, replacing all `{{variable}}` placeholders with user values
4. The resolved agent config (with no remaining placeholders) is sent to `POST /v1/agents`

**Supported filters** (implemented in Forge's template engine):

| Filter | Example | Result |
|--------|---------|--------|
| `slugify` | `{{company_name\|slugify}}` | `"Acme Corp"` → `"acme-corp"` |
| `lower` | `{{brand_voice\|lower}}` | `"Professional"` → `"professional"` |
| `upper` | `{{brand_voice\|upper}}` | `"professional"` → `"PROFESSIONAL"` |

The node API never sees template variables — it receives a fully resolved agent YAML.

### Template storage and API

- Templates stored in `config/templates/*.template.yaml`
- Forge reads templates from the node via:
  - `GET /v1/templates` — list all templates (name, display_name, category, description)
  - `GET /v1/templates/{name}` — full template detail including agent_config
- Future: community templates via Nexus marketplace

---

## Template Agent Definitions

Below are the complete agent configurations for each pre-built template.

### sales-qualifier.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: sales-qualifier
  version: "1.0.0"
  category: sales
  tags: [leads, bant, qualification, crm]

template:
  display_name: "Sales Lead Qualifier"
  description: >
    Qualifies incoming sales leads using BANT methodology (Budget, Authority, Need, Timeline).
    Scores leads 1-10 and recommends next actions. Integrates with CRM for company lookup.
  recommended_channels:
    - channel: whatsapp
      reason: "Direct lead engagement via business messaging"
    - channel: web_chat
      reason: "Embed in landing pages for inbound qualification"
  variables:
    - key: company_name
      label: "Your company name"
      placeholder: "Acme Corp"
      required: true
    - key: product_name
      label: "Product or service you sell"
      placeholder: "Cloud hosting solutions"
      required: true
    - key: brand_voice
      label: "Tone of communication"
      default: "Professional and consultative"

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{company_name|slugify}}-sales-qualifier"
      version: "1.0.0"
      namespace: sales
      labels:
        template: sales-qualifier
        team: revenue
    spec:
      identity:
        display_name: "{{company_name}} Sales Qualifier"
        description: "Qualifies leads for {{product_name}} using BANT"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.3
            top_p: 0.9
            max_tokens: 2048
        routing:
          strategy: cost_optimized
          health_check_interval: 30
      prompts:
        system: |
          You are a sales lead qualification assistant for {{company_name}}, selling {{product_name}}.
          Your communication style is: {{brand_voice}}.

          For each lead, assess using BANT methodology:
          - **Budget**: Can they afford {{product_name}}?
          - **Authority**: Are they the decision maker?
          - **Need**: Do they have a genuine need for {{product_name}}?
          - **Timeline**: When do they plan to purchase?

          Provide a qualification score (1-10) and recommended next action.
          Be conversational but focused on qualification.
      orchestration:
        pattern: react
        max_iterations: 5
        timeout_seconds: 60
      tools:
        - name: lookup_company
          type: internal
          description: "Look up company information from CRM"
          parameters:
            company_name:
              type: string
              description: "Company name to look up"
      memory:
        conversational:
          backend: redis
          strategy: sliding_window
          max_turns: 20
          ttl: 3600
      guardrails:
        input:
          - type: pii_detection
            action: redact
          - type: max_length
            max_chars: 5000
        output:
          - type: cost_limit
            max_tokens_per_turn: 1000
```

### product-advisor.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: product-advisor
  version: "1.0.0"
  category: sales
  tags: [products, recommendations, catalog, ecommerce]

template:
  display_name: "Product Advisor"
  description: >
    Recommends products based on customer needs. Asks discovery questions,
    matches to catalog, and generates side-by-side comparisons.
  recommended_channels:
    - channel: whatsapp
      reason: "Quick product consultations via messaging"
    - channel: telegram
      reason: "Rich media support for product images"
  variables:
    - key: company_name
      label: "Your company name"
      required: true
    - key: product_category
      label: "What type of products do you sell?"
      placeholder: "Electronics, furniture, software, etc."
      required: true
    - key: brand_voice
      label: "Tone of communication"
      default: "Friendly and knowledgeable"

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{company_name|slugify}}-product-advisor"
      version: "1.0.0"
      namespace: sales
      labels:
        template: product-advisor
    spec:
      identity:
        display_name: "{{company_name}} Product Advisor"
        description: "Recommends {{product_category}} based on customer needs"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.5
            max_tokens: 2048
        routing:
          strategy: cost_optimized
      prompts:
        system: |
          You are a product advisor for {{company_name}}, specializing in {{product_category}}.
          Your style is: {{brand_voice}}.

          Your job:
          1. Ask discovery questions to understand the customer's needs, budget, and preferences
          2. Recommend 2-3 products that match their criteria
          3. Explain pros/cons of each option
          4. Help them make a decision

          Never pressure the customer. Focus on finding the right fit.
      orchestration:
        pattern: react
        max_iterations: 8
        timeout_seconds: 60
      tools:
        - name: search_catalog
          type: rag
          description: "Search product catalog"
          parameters:
            query:
              type: string
              description: "Product search query"
      memory:
        conversational:
          backend: redis
          strategy: sliding_window
          max_turns: 30
          ttl: 7200
      guardrails:
        input:
          - type: pii_detection
            action: redact
        output:
          - type: cost_limit
            max_tokens_per_turn: 1500
```

### support-agent.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: support-agent
  version: "1.0.0"
  category: customer_service
  tags: [support, faq, knowledge-base, escalation]

template:
  display_name: "Support Agent"
  description: >
    Resolves FAQs using RAG-powered knowledge base. Escalates to human agent
    when confidence is low. Empathetic and professional tone.
  recommended_channels:
    - channel: whatsapp
      reason: "Most popular channel for customer support"
    - channel: telegram
      reason: "Real-time support conversations"
    - channel: web_chat
      reason: "Embed in website help center"
  variables:
    - key: company_name
      label: "Your company name"
      required: true
    - key: support_scope
      label: "What topics does your support cover?"
      placeholder: "Billing, technical issues, returns, general inquiries"
      required: true
    - key: escalation_contact
      label: "How to escalate to a human?"
      placeholder: "Email support@company.com or call +1-555-0100"
      default: "contact our support team directly"

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{company_name|slugify}}-support"
      version: "1.0.0"
      namespace: support
      labels:
        template: support-agent
    spec:
      identity:
        display_name: "{{company_name}} Support"
        description: "Customer support for {{support_scope}}"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.2
            max_tokens: 2048
        routing:
          strategy: quality_first
      prompts:
        system: |
          You are a customer support agent for {{company_name}}.
          You handle: {{support_scope}}.

          Guidelines:
          - Always be polite, professional, and empathetic
          - Use the knowledge base to answer questions accurately
          - If you don't know the answer, say so honestly
          - For issues you cannot resolve, escalate: {{escalation_contact}}
          - Never make up information about policies or procedures
      orchestration:
        pattern: plan_and_execute
        max_iterations: 8
        timeout_seconds: 60
      tools:
        - name: knowledge_search
          type: rag
          description: "Search company knowledge base for answers"
          parameters:
            query:
              type: string
              description: "Support question to search for"
      memory:
        conversational:
          backend: redis
          strategy: summary
          max_turns: 50
          ttl: 86400
        semantic:
          backend: chromadb
          similarity_threshold: 0.7
          max_results: 5
      guardrails:
        input:
          - type: pii_detection
            action: redact
        output:
          - type: pii_detection
            action: redact
          - type: cost_limit
            max_tokens_per_turn: 500
```

### returns-claims.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: returns-claims
  version: "1.0.0"
  category: customer_service
  tags: [returns, warranty, claims, orders]

template:
  display_name: "Returns & Claims"
  description: >
    Manages product returns and warranty claims. Collects order info,
    validates against return policy, and generates return instructions.
  recommended_channels:
    - channel: whatsapp
      reason: "Customers prefer messaging for return requests"
  variables:
    - key: company_name
      label: "Your company name"
      required: true
    - key: return_policy_days
      label: "Return window (days)"
      placeholder: "30"
      default: "30"
    - key: return_instructions
      label: "How should customers return products?"
      placeholder: "Ship to our warehouse at 123 Main St"
      required: true

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{company_name|slugify}}-returns"
      version: "1.0.0"
      namespace: support
      labels:
        template: returns-claims
    spec:
      identity:
        display_name: "{{company_name}} Returns"
        description: "Handles returns and warranty claims"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.1
            max_tokens: 1500
        routing:
          strategy: quality_first
      prompts:
        system: |
          You are a returns and claims assistant for {{company_name}}.
          Return policy: {{return_policy_days}} days from purchase.

          Process:
          1. Ask for order number or purchase details
          2. Verify the order exists and is within return window
          3. Ask for reason of return
          4. If eligible, provide return instructions: {{return_instructions}}
          5. If not eligible, explain why and offer alternatives

          Be empathetic but follow policy strictly. Never approve returns outside policy
          without escalating to a supervisor.
      orchestration:
        pattern: react
        max_iterations: 6
        timeout_seconds: 45
      tools:
        - name: lookup_order
          type: internal
          description: "Look up order by order number"
          parameters:
            order_number:
              type: string
              description: "Order number to look up"
      memory:
        conversational:
          backend: redis
          strategy: sliding_window
          max_turns: 20
          ttl: 3600
      guardrails:
        input:
          - type: pii_detection
            action: redact
        output:
          - type: pii_detection
            action: redact
```

### payment-reminder.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: payment-reminder
  version: "1.0.0"
  category: collections
  tags: [payments, reminders, billing, plans]

template:
  display_name: "Payment Reminder"
  description: >
    Sends payment reminders with configurable escalation. Friendly first notice,
    firmer follow-ups. Can negotiate payment plans for overdue accounts.
  recommended_channels:
    - channel: whatsapp
      reason: "High open rates for payment notifications"
  variables:
    - key: company_name
      label: "Your company name"
      required: true
    - key: payment_methods
      label: "Accepted payment methods"
      placeholder: "Bank transfer, credit card, PayPal"
      required: true
    - key: support_contact
      label: "Contact for payment issues"
      placeholder: "billing@company.com or +1-555-0100"
      required: true

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{company_name|slugify}}-payment-reminder"
      version: "1.0.0"
      namespace: collections
      labels:
        template: payment-reminder
    spec:
      identity:
        display_name: "{{company_name}} Payment Reminder"
        description: "Payment reminders and plan negotiation"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.2
            max_tokens: 1024
        routing:
          strategy: cost_optimized
      prompts:
        system: |
          You are a payment reminder assistant for {{company_name}}.

          Accepted payment methods: {{payment_methods}}.
          For issues, contact: {{support_contact}}.

          Escalation levels:
          1. First reminder: Friendly, informative. "Hi! Just a reminder that your payment is due."
          2. Second reminder: Polite but firm. "We noticed your payment is overdue."
          3. Third reminder: Urgent. "Action required: your account has an outstanding balance."

          If the customer asks for a payment plan, you may offer installment options
          (2-4 monthly payments). Always confirm the arrangement clearly.

          Never be aggressive or threatening. Maintain professionalism at all times.
      orchestration:
        pattern: react
        max_iterations: 5
        timeout_seconds: 30
      tools:
        - name: check_balance
          type: internal
          description: "Check outstanding balance for a customer"
          parameters:
            customer_id:
              type: string
              description: "Customer ID or account number"
      memory:
        conversational:
          backend: redis
          strategy: sliding_window
          max_turns: 15
          ttl: 86400
      guardrails:
        input:
          - type: pii_detection
            action: redact
        output:
          - type: content_filter
            blocked_categories: [harassment, threats]
```

### debt-collector.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: debt-collector
  version: "1.0.0"
  category: collections
  tags: [debt, collection, follow-up, commitments]

template:
  display_name: "Debt Collector"
  description: >
    Structured debt follow-up. Generates payment commitments, tracks promises,
    escalates non-responsive accounts. Compliant and professional.
  recommended_channels:
    - channel: whatsapp
      reason: "Direct debtor communication"
    - channel: telegram
      reason: "Alternative messaging channel"
  variables:
    - key: company_name
      label: "Your company name"
      required: true
    - key: legal_notice
      label: "Legal compliance notice"
      placeholder: "This is an attempt to collect a debt..."
      required: true
    - key: payment_methods
      label: "Accepted payment methods"
      required: true

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{company_name|slugify}}-debt-collector"
      version: "1.0.0"
      namespace: collections
      labels:
        template: debt-collector
    spec:
      identity:
        display_name: "{{company_name}} Collections"
        description: "Debt collection and payment commitment tracking"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.1
            max_tokens: 1024
        routing:
          strategy: quality_first
      prompts:
        system: |
          You are a collections specialist for {{company_name}}.

          Legal notice (include in first message): {{legal_notice}}
          Payment methods: {{payment_methods}}.

          Process:
          1. Identify the debtor and verify the outstanding amount
          2. Present the debt clearly and professionally
          3. Offer payment options (full payment or installment plan)
          4. If they commit to pay, confirm date and amount clearly
          5. If they dispute, collect details and escalate to review

          Rules:
          - Never harass, threaten, or use abusive language
          - Respect contact hour restrictions
          - Always include the legal compliance notice in first contact
          - Document all commitments made
      orchestration:
        pattern: react
        max_iterations: 6
        timeout_seconds: 45
      tools:
        - name: check_debt
          type: internal
          description: "Look up debt details for a customer"
          parameters:
            customer_id:
              type: string
              description: "Customer or account ID"
        - name: record_commitment
          type: internal
          description: "Record a payment commitment"
          parameters:
            customer_id:
              type: string
            amount:
              type: number
            due_date:
              type: string
              description: "ISO date when payment is promised"
      memory:
        conversational:
          backend: redis
          strategy: sliding_window
          max_turns: 20
          ttl: 604800
      guardrails:
        input:
          - type: pii_detection
            action: redact
        output:
          - type: content_filter
            blocked_categories: [harassment, threats, discrimination]
          - type: cost_limit
            max_tokens_per_turn: 500
```

### campaign-bot.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: campaign-bot
  version: "1.0.0"
  category: marketing
  tags: [campaigns, promotions, leads, engagement]

template:
  display_name: "Campaign Bot"
  description: >
    Sends promotional campaigns, segments responses by interest,
    and captures leads from engagement.
  recommended_channels:
    - channel: telegram
      reason: "Rich media support for promotional content"
    - channel: whatsapp
      reason: "High engagement rates for promotions"
  variables:
    - key: company_name
      label: "Your company name"
      required: true
    - key: campaign_description
      label: "What is this campaign about?"
      placeholder: "Summer sale, new product launch, seasonal offer"
      required: true
    - key: offer_details
      label: "Offer details"
      placeholder: "20% off all products until March 31"
      required: true

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{company_name|slugify}}-campaign"
      version: "1.0.0"
      namespace: marketing
      labels:
        template: campaign-bot
    spec:
      identity:
        display_name: "{{company_name}} Campaign"
        description: "Promotional campaign: {{campaign_description}}"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.7
            max_tokens: 1024
        routing:
          strategy: cost_optimized
      prompts:
        system: |
          You are a marketing assistant for {{company_name}}.
          Current campaign: {{campaign_description}}.
          Offer: {{offer_details}}.

          Your job:
          1. Engage customers with the current promotion
          2. Answer questions about the offer
          3. Capture interest and contact details for follow-up
          4. Segment responses: "interested", "maybe later", "not interested"

          Be enthusiastic but not pushy. Respect when someone says no.
      orchestration:
        pattern: react
        max_iterations: 5
        timeout_seconds: 30
      memory:
        conversational:
          backend: redis
          strategy: sliding_window
          max_turns: 15
          ttl: 3600
      guardrails:
        output:
          - type: cost_limit
            max_tokens_per_turn: 500
```

### brand-chef.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: brand-chef
  version: "1.0.0"
  category: food_and_beverage
  tags: [recipes, cooking, food, brand, chef]

template:
  display_name: "Brand Chef"
  description: >
    Recommends recipes using the brand's products. Cooking tips, meal planning,
    and ingredient substitutions. Personalized to user preferences and dietary restrictions.
  recommended_channels:
    - channel: whatsapp
      reason: "Quick recipe consultations while shopping or cooking"
    - channel: instagram
      reason: "Visual platform aligned with food content"
  variables:
    - key: brand_name
      label: "Your brand name"
      required: true
    - key: product_list
      label: "Main products (comma-separated)"
      placeholder: "Premium butter, cooking cream, margarine, cheese spread"
      required: true
    - key: chef_persona
      label: "Chef personality"
      default: "Friendly home cook who loves sharing family recipes"

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{brand_name|slugify}}-chef"
      version: "1.0.0"
      namespace: food
      labels:
        template: brand-chef
    spec:
      identity:
        display_name: "Chef {{brand_name}}"
        description: "Recipe assistant featuring {{brand_name}} products"
        avatar: "chef"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.7
            max_tokens: 2048
        routing:
          strategy: cost_optimized
      prompts:
        system: |
          You are Chef {{brand_name}}, a {{chef_persona}}.

          You specialize in recipes using {{brand_name}} products: {{product_list}}.

          Guidelines:
          - Always feature at least one {{brand_name}} product in your recipes
          - Ask about dietary restrictions and preferences
          - Provide step-by-step instructions with cooking tips
          - Suggest ingredient substitutions when asked
          - Share meal planning ideas for the week
          - Be warm, encouraging, and passionate about cooking

          When sharing recipes, format them clearly:
          - Ingredients list with quantities
          - Step-by-step instructions
          - Cooking time and difficulty level
          - Tips for best results with {{brand_name}} products
      orchestration:
        pattern: react
        max_iterations: 5
        timeout_seconds: 45
      tools:
        - name: recipe_search
          type: rag
          description: "Search recipe database"
          parameters:
            query:
              type: string
              description: "Recipe search (ingredients, cuisine, dish type)"
      memory:
        conversational:
          backend: redis
          strategy: sliding_window
          max_turns: 25
          ttl: 7200
        semantic:
          backend: chromadb
          similarity_threshold: 0.7
          max_results: 5
      guardrails:
        output:
          - type: topic_filter
            allowed_topics: [cooking, recipes, food, nutrition, meal_planning]
          - type: cost_limit
            max_tokens_per_turn: 1500
```

### nutritionist.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: nutritionist
  version: "1.0.0"
  category: food_and_beverage
  tags: [nutrition, health, dietary, allergens]

template:
  display_name: "Nutritionist"
  description: >
    Nutritional information about products. Dietary recommendations,
    allergen alerts, and healthy combinations.
  recommended_channels:
    - channel: web_chat
      reason: "Detailed nutritional consultations with rich formatting"
  variables:
    - key: brand_name
      label: "Your brand name"
      required: true
    - key: product_list
      label: "Products with nutritional focus"
      placeholder: "Low-fat yogurt, whole grain bread, protein bars"
      required: true
    - key: disclaimer
      label: "Health disclaimer"
      default: "This is general nutritional guidance, not medical advice. Consult a healthcare professional for dietary concerns."

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{brand_name|slugify}}-nutritionist"
      version: "1.0.0"
      namespace: food
      labels:
        template: nutritionist
    spec:
      identity:
        display_name: "{{brand_name}} Nutritionist"
        description: "Nutritional guidance for {{brand_name}} products"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.2
            max_tokens: 2048
        routing:
          strategy: quality_first
      prompts:
        system: |
          You are a nutritionist assistant for {{brand_name}}.
          Products: {{product_list}}.

          Disclaimer (include when giving dietary advice): {{disclaimer}}

          You can:
          - Provide nutritional information about {{brand_name}} products
          - Alert about allergens (gluten, dairy, nuts, etc.)
          - Suggest healthy product combinations
          - Recommend products for specific dietary needs (keto, vegan, low-sodium, etc.)
          - Compare nutritional values between products

          Never diagnose medical conditions or replace professional medical advice.
      orchestration:
        pattern: react
        max_iterations: 5
        timeout_seconds: 30
      tools:
        - name: nutrition_lookup
          type: rag
          description: "Look up nutritional information for products"
          parameters:
            product:
              type: string
              description: "Product name to look up"
      memory:
        conversational:
          backend: redis
          strategy: sliding_window
          max_turns: 20
          ttl: 3600
      guardrails:
        output:
          - type: topic_filter
            allowed_topics: [nutrition, food, health, dietary]
          - type: cost_limit
            max_tokens_per_turn: 1000
```

### service-scheduler.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: service-scheduler
  version: "1.0.0"
  category: automotive
  tags: [workshop, appointments, maintenance, repairs, vehicles]

template:
  display_name: "Service Scheduler"
  description: >
    Schedules workshop appointments. Reminds preventive maintenance based on mileage.
    Receives problem photos for pre-diagnosis. Manages service calendar.
  recommended_channels:
    - channel: whatsapp
      reason: "Customers can send photos of car issues directly"
    - channel: web_chat
      reason: "Embed in dealership or workshop website"
  variables:
    - key: workshop_name
      label: "Workshop or dealership name"
      required: true
    - key: services_offered
      label: "Services offered"
      placeholder: "Oil change, brake repair, tire rotation, engine diagnostics, body work"
      required: true
    - key: business_hours
      label: "Business hours"
      placeholder: "Mon-Fri 8am-6pm, Sat 9am-2pm"
      required: true
    - key: location
      label: "Workshop address"
      required: true

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{workshop_name|slugify}}-scheduler"
      version: "1.0.0"
      namespace: automotive
      labels:
        template: service-scheduler
    spec:
      identity:
        display_name: "{{workshop_name}} Service Scheduler"
        description: "Workshop appointment scheduling and maintenance reminders"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.2
            max_tokens: 1500
        routing:
          strategy: quality_first
      prompts:
        system: |
          You are the service scheduler for {{workshop_name}}.
          Location: {{location}}.
          Business hours: {{business_hours}}.
          Services: {{services_offered}}.

          Your responsibilities:
          1. Schedule service appointments based on available slots
          2. Collect vehicle info: make, model, year, mileage
          3. Ask about the issue (description + photos if available)
          4. Recommend preventive maintenance based on mileage:
             - 5,000 km: Oil change
             - 10,000 km: Oil + filters
             - 20,000 km: Major service (brakes, fluids, belts)
             - 40,000 km: Full inspection
          5. Confirm appointment details: date, time, service type, estimated duration
          6. Send reminders for upcoming appointments

          If a customer sends a photo of an issue, describe what you see and recommend
          whether it needs immediate attention or can wait for a scheduled visit.
      orchestration:
        pattern: react
        max_iterations: 8
        timeout_seconds: 60
      tools:
        - name: check_availability
          type: internal
          description: "Check available appointment slots"
          parameters:
            date:
              type: string
              description: "Date to check (ISO format)"
            service_type:
              type: string
              description: "Type of service requested"
        - name: book_appointment
          type: internal
          description: "Book a service appointment"
          parameters:
            customer_name:
              type: string
            vehicle_info:
              type: string
            service_type:
              type: string
            date:
              type: string
            time:
              type: string
      memory:
        conversational:
          backend: redis
          strategy: sliding_window
          max_turns: 20
          ttl: 86400
      guardrails:
        input:
          - type: pii_detection
            action: redact
        output:
          - type: cost_limit
            max_tokens_per_turn: 800
```

### parts-advisor.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: parts-advisor
  version: "1.0.0"
  category: automotive
  tags: [parts, repairs, quotes, vehicles, inventory]

template:
  display_name: "Parts Advisor"
  description: >
    Checks parts availability, generates quotes, and schedules installation.
    Compatible parts lookup by vehicle make/model/year.
  recommended_channels:
    - channel: whatsapp
      reason: "Quick parts inquiries and quote requests"
  variables:
    - key: business_name
      label: "Business name"
      required: true
    - key: specialization
      label: "Vehicle specialization (if any)"
      placeholder: "All brands, or specific: Toyota, Honda, European cars"
      default: "All vehicle brands"
    - key: location
      label: "Store address"
      required: true

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{business_name|slugify}}-parts"
      version: "1.0.0"
      namespace: automotive
      labels:
        template: parts-advisor
    spec:
      identity:
        display_name: "{{business_name}} Parts"
        description: "Auto parts availability and quotes"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.1
            max_tokens: 1500
        routing:
          strategy: quality_first
      prompts:
        system: |
          You are a parts advisor for {{business_name}}.
          Specialization: {{specialization}}.
          Location: {{location}}.

          Your responsibilities:
          1. Ask for vehicle details: make, model, year, engine
          2. Identify the part needed from the customer's description
          3. Check inventory for compatible parts (OEM and aftermarket)
          4. Provide quotes with part options (good/better/best)
          5. Schedule installation if requested
          6. Suggest related parts that may also need replacement

          Always verify vehicle compatibility before quoting.
          If a part is out of stock, provide estimated delivery time.
      orchestration:
        pattern: react
        max_iterations: 6
        timeout_seconds: 45
      tools:
        - name: search_parts
          type: internal
          description: "Search parts inventory by vehicle and part type"
          parameters:
            vehicle_make:
              type: string
            vehicle_model:
              type: string
            vehicle_year:
              type: integer
            part_type:
              type: string
              description: "Type of part (brake pads, oil filter, etc.)"
        - name: get_quote
          type: internal
          description: "Generate a quote for parts and installation"
          parameters:
            parts:
              type: array
              description: "List of part IDs to quote"
            include_installation:
              type: boolean
      memory:
        conversational:
          backend: redis
          strategy: sliding_window
          max_turns: 20
          ttl: 7200
      guardrails:
        input:
          - type: pii_detection
            action: redact
        output:
          - type: cost_limit
            max_tokens_per_turn: 800
```

### property-agent.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: property-agent
  version: "1.0.0"
  category: real_estate
  tags: [properties, listings, viewings, real-estate]

template:
  display_name: "Property Agent"
  description: >
    Qualifies interested buyers/renters. Matches preferences to listings.
    Schedules property viewings.
  recommended_channels:
    - channel: whatsapp
      reason: "Quick property inquiries and viewing scheduling"
  variables:
    - key: agency_name
      label: "Real estate agency name"
      required: true
    - key: service_area
      label: "Areas you cover"
      placeholder: "Downtown, suburbs, beachfront properties"
      required: true
    - key: property_types
      label: "Property types"
      placeholder: "Apartments, houses, commercial, land"
      default: "Apartments, houses, commercial spaces"

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{agency_name|slugify}}-property"
      version: "1.0.0"
      namespace: real_estate
      labels:
        template: property-agent
    spec:
      identity:
        display_name: "{{agency_name}} Property Finder"
        description: "Property search and viewing scheduling in {{service_area}}"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.4
            max_tokens: 2048
        routing:
          strategy: cost_optimized
      prompts:
        system: |
          You are a property agent for {{agency_name}}.
          Areas: {{service_area}}.
          Property types: {{property_types}}.

          Process:
          1. Qualify the lead: buying or renting? Budget? Timeline?
          2. Understand preferences: location, size, bedrooms, amenities
          3. Search and recommend matching properties (2-3 options)
          4. For interested leads, schedule viewings
          5. Follow up after viewings for feedback

          Be professional but warm. Never pressure clients.
          If no matching properties, be honest and offer to notify when new listings match.
      orchestration:
        pattern: react
        max_iterations: 8
        timeout_seconds: 60
      tools:
        - name: search_listings
          type: rag
          description: "Search property listings"
          parameters:
            query:
              type: string
              description: "Property search criteria"
        - name: schedule_viewing
          type: internal
          description: "Schedule a property viewing"
          parameters:
            property_id:
              type: string
            customer_name:
              type: string
            preferred_date:
              type: string
      memory:
        conversational:
          backend: redis
          strategy: sliding_window
          max_turns: 25
          ttl: 604800
      guardrails:
        input:
          - type: pii_detection
            action: redact
```

### tutor-assistant.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: tutor-assistant
  version: "1.0.0"
  category: education
  tags: [tutoring, homework, learning, education]

template:
  display_name: "Tutor Assistant"
  description: >
    Homework help, concept explanations, and practice exercises.
    Adapts to student level and learning pace.
  recommended_channels:
    - channel: telegram
      reason: "Students prefer Telegram for academic communication"
    - channel: web_chat
      reason: "Embed in school or academy website"
  variables:
    - key: institution_name
      label: "School or academy name"
      required: true
    - key: subjects
      label: "Subjects covered"
      placeholder: "Math, Science, English, History"
      required: true
    - key: education_level
      label: "Education level"
      placeholder: "Elementary, middle school, high school, university"
      default: "Middle school and high school"

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{institution_name|slugify}}-tutor"
      version: "1.0.0"
      namespace: education
      labels:
        template: tutor-assistant
    spec:
      identity:
        display_name: "{{institution_name}} Tutor"
        description: "Tutoring in {{subjects}} for {{education_level}}"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.3
            max_tokens: 2048
        routing:
          strategy: quality_first
      prompts:
        system: |
          You are a tutor for {{institution_name}}.
          Subjects: {{subjects}}.
          Level: {{education_level}}.

          Teaching approach:
          - Ask the student what they're working on and what they find confusing
          - Explain concepts step by step, using simple language
          - Use examples and analogies appropriate for their level
          - Don't give direct answers to homework — guide them to find the answer
          - Offer practice exercises to reinforce learning
          - Celebrate progress and encourage effort

          Never do the homework for the student. Help them understand so they can do it themselves.
      orchestration:
        pattern: react
        max_iterations: 10
        timeout_seconds: 90
      tools:
        - name: knowledge_search
          type: rag
          description: "Search educational content database"
          parameters:
            query:
              type: string
              description: "Topic or concept to search"
      memory:
        conversational:
          backend: redis
          strategy: summary
          max_turns: 50
          ttl: 86400
      guardrails:
        output:
          - type: content_filter
            blocked_categories: [violence, adult_content]
          - type: cost_limit
            max_tokens_per_turn: 1500
```

### hr-assistant.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: hr-assistant
  version: "1.0.0"
  category: internal_ops
  tags: [hr, human-resources, policies, vacations, benefits]

template:
  display_name: "HR Assistant"
  description: >
    Answers HR questions about policies, vacation balance, and benefits.
    Routes complex requests to HR team.
  recommended_channels:
    - channel: slack
      reason: "Internal team communication"
    - channel: web_chat
      reason: "Embed in company intranet"
  variables:
    - key: company_name
      label: "Your company name"
      required: true
    - key: hr_contact
      label: "HR team contact"
      placeholder: "hr@company.com or #hr-team on Slack"
      required: true
    - key: policies_summary
      label: "Key policies to know about"
      placeholder: "Remote work, vacation (20 days/year), sick leave, expense reports"
      required: true

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{company_name|slugify}}-hr"
      version: "1.0.0"
      namespace: internal
      labels:
        template: hr-assistant
    spec:
      identity:
        display_name: "{{company_name}} HR Assistant"
        description: "HR policy questions and request routing"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.2
            max_tokens: 1500
        routing:
          strategy: quality_first
      prompts:
        system: |
          You are the HR assistant for {{company_name}}.
          HR contact for complex issues: {{hr_contact}}.

          Key policies: {{policies_summary}}.

          You can help with:
          - Policy questions (vacation, sick leave, remote work, benefits)
          - Vacation balance inquiries
          - Expense report process
          - Onboarding information
          - General workplace questions

          For sensitive topics (complaints, performance issues, salary negotiations),
          direct employees to {{hr_contact}}.

          Be helpful, confidential, and professional. Never share one employee's
          information with another.
      orchestration:
        pattern: react
        max_iterations: 5
        timeout_seconds: 30
      tools:
        - name: policy_search
          type: rag
          description: "Search company policy documents"
          parameters:
            query:
              type: string
              description: "Policy topic to search"
      memory:
        conversational:
          backend: redis
          strategy: sliding_window
          max_turns: 15
          ttl: 3600
      guardrails:
        input:
          - type: pii_detection
            action: redact
        output:
          - type: pii_detection
            action: redact
```

### onboarding-buddy.template.yaml

```yaml
apiVersion: astromesh/v1
kind: AgentTemplate
metadata:
  name: onboarding-buddy
  version: "1.0.0"
  category: internal_ops
  tags: [onboarding, new-hire, setup, checklist]

template:
  display_name: "Onboarding Buddy"
  description: >
    Guides new employees through their first weeks. Checklist tracking,
    team introductions, tool setup help.
  recommended_channels:
    - channel: slack
      reason: "New hires already onboarding into Slack"
  variables:
    - key: company_name
      label: "Your company name"
      required: true
    - key: tools_used
      label: "Tools new hires need to set up"
      placeholder: "Slack, GitHub, Jira, Google Workspace, VPN"
      required: true
    - key: key_contacts
      label: "Key contacts for new hires"
      placeholder: "IT: it@company.com, Facilities: office@company.com"
      required: true

  agent_config:
    apiVersion: astromesh/v1
    kind: Agent
    metadata:
      name: "{{company_name|slugify}}-onboarding"
      version: "1.0.0"
      namespace: internal
      labels:
        template: onboarding-buddy
    spec:
      identity:
        display_name: "{{company_name}} Onboarding Buddy"
        description: "New employee onboarding guide"
        avatar: "buddy"
      model:
        primary:
          provider: ollama
          model: "llama3.1:8b"
          endpoint: "http://ollama:11434"
          parameters:
            temperature: 0.5
            max_tokens: 1500
        routing:
          strategy: cost_optimized
      prompts:
        system: |
          You are the onboarding buddy for {{company_name}}. Welcome new hires!

          Tools to set up: {{tools_used}}.
          Key contacts: {{key_contacts}}.

          First week checklist:
          - [ ] Welcome and introductions
          - [ ] Set up all required tools
          - [ ] Review company handbook
          - [ ] Meet your team lead
          - [ ] Complete required training
          - [ ] Set up development environment (if engineering)

          Be friendly, patient, and encouraging. New hires have lots of questions —
          no question is too small. Track their progress through the checklist and
          celebrate when they complete milestones.
      orchestration:
        pattern: react
        max_iterations: 5
        timeout_seconds: 30
      tools:
        - name: checklist_search
          type: rag
          description: "Search onboarding documentation"
          parameters:
            query:
              type: string
              description: "Onboarding topic to search"
      memory:
        conversational:
          backend: redis
          strategy: summary
          max_turns: 100
          ttl: 2592000
      guardrails:
        output:
          - type: cost_limit
            max_tokens_per_turn: 800
```

---

## Dashboard

### Agent list view

Main screen when entering Forge. Lists all agents on the connected node.

| Column | Detail |
|--------|--------|
| Name | display_name + technical name |
| Origin | "From scratch" / template name used |
| Status | `draft` · `deployed` · `paused` |
| Target | Local / Remote node (URL) / Nexus |
| Last edited | Timestamp |
| Actions | Edit (wizard or canvas) · Deploy · Pause · Delete |

### Quick actions

- **"Create from Scratch"** → opens empty wizard
- **"Start from Template"** → opens gallery
- **"Import YAML"** → uploads a `.agent.yaml` file, opens in wizard/canvas

---

## Deploy Flow

When deploying from wizard or canvas:

```
Review YAML → Select Target → Confirm → Deploy
```

### Target selection

- **Local** (default) — `POST /v1/agents` to the connected node. If agent already exists, `PUT` to update.
- **Remote Node** — input URL + API key. Forge runs health check (`GET /v1/system`) before deploying.
- **Nexus** (future) — button visible but disabled with "Coming Soon" badge in v1.

### Post-deploy

- Success: confirmation with agent status on the node
- Failure: error from API with suggested corrections
- Agent status updates in dashboard

---

## Node Connection

### First load

If embedded, no configuration needed (relative URLs). If standalone, Forge prompts for the node URL.

### Settings (accessible from header)

- Node URL
- API key (optional, for authenticated nodes)

### Connection indicator

Always visible in header: green dot (connected) / red dot (disconnected).

If connection is lost, Forge shows a banner warning. Editing continues but save/deploy is disabled until reconnection.

---

## New Core API Requirements

Changes needed in the existing Astromesh runtime:

### New endpoints

- `PUT /v1/agents/{name}` — Update an existing agent's configuration (partial or full update)
- `POST /v1/agents/{name}/deploy` — Deploy a draft/paused agent to the runtime (loads into `_agents` dict, sets status to `deployed`)
- `POST /v1/agents/{name}/pause` — Pause a deployed agent (unloads from `_agents` dict, sets status to `paused`)
- `GET /v1/templates` — List available templates from `config/templates/`
- `GET /v1/templates/{name}` — Return full template detail

### New configuration

- `services.forge: true/false` in node config to enable/disable serving Forge static files
- `cors_origins` in `config/runtime.yaml` for standalone mode CORS

### Existing endpoints used as-is

- `GET /v1/agents` — List agents
- `POST /v1/agents` — Create agent
- `GET /v1/agents/{name}` — Get agent detail
- `DELETE /v1/agents/{name}` — Delete agent
- `GET /v1/tools` — List available tools
- `GET /v1/system` — Health check

---

## Migration from Astromesh Cloud

| Cloud component | Forge equivalent |
|----------------|-----------------|
| `astromesh-cloud/web/` (Next.js Studio) | `astromesh-forge/` (Vite + React SPA) |
| `astromesh-cloud/api/` (Cloud API) | **Deprecated** — core API already has agent CRUD |
| Studio wizard (5 steps) | Forge wizard (7 steps) + canvas |
| Cloud DB (PostgreSQL) | Not needed — state lives in the node |
| Auth (JWT/OAuth) | Deferred to Nexus |
| Orgs/tenancy | Deferred to Nexus |
| Usage tracking | Deferred to Cortex |

---

## Future: Nexus Integration

When Nexus (managed cloud) launches:

- Forge adds Nexus as a deploy target
- Nexus provides auth, orgs, billing, tenancy
- Forge authenticates against Nexus API instead of node API
- Community templates marketplace hosted on Nexus
- Same SPA, different target URL
