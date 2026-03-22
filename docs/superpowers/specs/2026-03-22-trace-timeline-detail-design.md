# Trace Timeline Detail Panel — Design Spec

## Problem

The Trace Timeline in astromesh-forge currently shows only token counts, duration bars, and status badges per span. For debugging the core runtime, developers need full visibility into the execution pipeline: model/provider info, prompts, responses, tool call arguments and results, orchestration steps (thought/action/observation), guardrail results, errors, and span events.

### Existing Data Flow Issue

There is a pre-existing mismatch between backend and frontend attribute conventions:

- **Backend** (`engine.py`): sets **flat** attributes via `span.set_attribute("input_tokens", value)` → stored in `span.attributes["input_tokens"]`
- **Frontend** (`SpanNode.tsx`, `TraceTimeline.tsx`): reads **nested** attributes like `span.attributes.metadata.usage.prompt_tokens`

This mismatch means some data already isn't displayed correctly. This spec standardizes on **flat attributes** (matching the backend `Span.set_attribute()` design) and fixes the frontend to read flat keys.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Detail location | Split panel (timeline top, detail bottom) | Keeps trace context visible while inspecting a span |
| Inline expansion | Chips/badges only (no text) | Keeps timeline clean and scaneable |
| Tab visibility | Fixed tabs, grayed out when empty | Consistent layout + visual signal of available data |
| Attribute convention | Flat scalar keys; structured values as dicts | Matches `Span.set_attribute()` semantics. Scalar values are flat keys; grouped data (`orch_step`, `tool_args`) stored as dicts since they represent a single logical unit |
| Guardrail data | Span events (not attributes) | Guardrails are point-in-time occurrences; events fit naturally. Note: guardrail execution is not yet wired in `engine.py` — tab will be grayed out until that pipeline stage is implemented |
| Large content (prompt/response) | Truncated in attributes, full via lazy expand | Prevents trace payloads from ballooning |

## Architecture

### Layout: Split Right Panel

```
┌──────────────────────────────────┐
│  Trace Timeline (scrollable)     │
│  ├─ 🤖 agent.run         2.4s   │
│  │  ├─ 🧠 memory_build   0.2s   │
│  │  ├─ 📝 prompt_render   50ms   │
│  │  ├─ ⚡ llm.complete  💬🔧 1.3s│  ← chips indicate available data
│  │  ├─ 🔧 tool.search    ✅ 0.7s│
│  │  ├─ ⚡ llm.complete  💬  0.2s│
│  │  └─ 💾 memory_persist  80ms   │
├──────────── resize handle ───────┤
│  Detail Panel (selected span)    │
│  [Overview][Input][Output]...    │
│  ┌────────────────────────────┐  │
│  │ Model: gpt-4o-mini         │  │
│  │ Provider: openai            │  │
│  │ Tokens: 1,245↑ 602↓        │  │
│  │ Orchestration: ReAct #1     │  │
│  │  💭 thought → 🔧 action    │  │
│  └────────────────────────────┘  │
└──────────────────────────────────┘
```

### Chip Indicators on Spans

Small icon badges displayed inline on each span row. Clicking a chip opens the detail panel on the corresponding tab.

| Chip | Meaning | Opens Tab |
|------|---------|-----------|
| 💬 | Has response/content | Output |
| 🔧 | Has tool calls | Tool Calls |
| ✅ | Has successful result | Output |
| 📋 | Has events | Events |
| ⚠️ | Has error | Overview (error section) |
| 🛡️ | Guardrails applied | Guardrails |

Chip derivation from **flat** span attributes:
- `💬` → `attributes.response` is a non-empty string
- `🔧` → `attributes.tool_calls` is a non-empty array
- `✅` → span name starts with `tool.` and `status === "ok"`
- `📋` → `events` array is non-empty
- `⚠️` → `status === "error"`
- `🛡️` → `events` array contains at least one event with `name === "guardrail"`

### Detail Panel Tabs

7 fixed tabs. Tabs with no data for the selected span are rendered with muted text and `cursor: not-allowed`.

#### 1. Overview
- **Metrics grid**: model, provider, latency (ms), cost ($) — from `attributes.*`
- **Token usage**: input ↑, output ↓, total — from `attributes.input_tokens`/`output_tokens`
- **Orchestration steps** (for `orchestration` spans): rendered from `span.events` where `event.name === "orch_step"`. Each step shows thought/action/action_input/observation as colored left-border blocks
- **Response preview** (for `llm.complete` spans): truncated first ~200 chars of `attributes.response` with link to Output tab
- **Error** (if status=error): error message from `attributes.error_message`

#### 2. Input
- Full rendered prompt sent to the model
- Source: `attributes.prompt`
- Rendered as preformatted text with word-wrap

#### 3. Output
- Full model response content
- Source: `attributes.response`
- Rendered as preformatted text

#### 4. Tool Calls
- For `llm.complete` spans: tool calls requested by the model — `attributes.tool_calls` array
- For `tool.call` spans: tool name from `attributes.tool`, input from `attributes.tool_args`, result from `attributes.tool_result`
- Arguments and results rendered as formatted JSON

#### 5. Guardrails
- Populated from `span.events` where `event.name === "guardrail"`
- Each event shows: guardrail name, type (input/output), action (pass/redact/block), details
- Empty when no guardrail events exist (tab grayed out)

#### 6. Events
- Chronological list of all `span.events`
- Each event: timestamp (relative to span start), name, attributes
- Rendered as a mini-timeline within the tab

#### 7. Raw
- Full JSON dump of `span.attributes` + `span.events`
- Collapsible tree view with copy-to-clipboard button

## Attribute Contract

All span attributes are **flat keys** on `span.attributes`. No nesting under `metadata`.

### Existing attributes (already set in engine.py)

| Key | Type | Set on spans | Description |
|-----|------|-------------|-------------|
| `agent` | `string` | `agent.run` | Agent name |
| `session` | `string` | `agent.run` | Session ID |
| `input_tokens` | `number` | `llm.complete` | Prompt token count |
| `output_tokens` | `number` | `llm.complete` | Completion token count |
| `tool` | `string` | `tool.call` | Tool name |
| `pattern` | `string` | `orchestration` | Orchestration pattern name |

### New attributes to add

| Key | Type | Set on spans | Source |
|-----|------|-------------|--------|
| `model` | `string` | `llm.complete` | `CompletionResponse.model` |
| `provider` | `string` | `llm.complete` | `CompletionResponse.provider` |
| `latency_ms` | `number` | `llm.complete` | `CompletionResponse.latency_ms` |
| `cost` | `number` | `llm.complete` | `CompletionResponse.cost` |
| `prompt` | `string` | `llm.complete` | Rendered prompt (truncated to 10,000 chars) |
| `response` | `string` | `llm.complete` | `CompletionResponse.content` (truncated to 10,000 chars) |
| `tool_calls` | `list[dict]` | `llm.complete` | Normalized from `CompletionResponse.tool_calls` (see normalization below) |
| `tool_args` | `dict` | `tool.call` | Tool input arguments (structured value — intentional dict, not flat) |
| `tool_result` | `string` | `tool.call` | Tool execution result (truncated to 5,000 chars) |
| `error_message` | `string` | any (on error) | Exception message |

### Orchestration step data (stored as events, not attributes)

Orchestration steps are stored as **events** on the `orchestration` span (via `orch_span.add_event("orch_step", {...})`), not as flat attributes. Each event contains: `{iteration, pattern, thought?, action?, action_input?, observation?, result?}`. This is because:
- Multiple steps map to multiple events (a single attribute can't hold N steps)
- Events have timestamps, showing when each step occurred
- This matches the guardrails pattern (also events)

### Truncation strategy

Large text fields (prompt, response, tool_result, observation) are truncated in span attributes to prevent trace payload bloat. Truncation limits:
- `prompt`: 10,000 chars
- `response`: 10,000 chars
- `tool_result`: 5,000 chars
- `observation`: 5,000 chars

Truncated values end with `\n... [truncated at N chars]`. The Raw tab shows the stored (truncated) value.

## Backend Changes Required

### 1. Enrich `llm.complete` span attributes (`engine.py`)

After receiving `CompletionResponse`, add to the existing `llm_span`:

```python
# Existing (already set):
llm_span.set_attribute("input_tokens", response.usage.get("input_tokens", 0))
llm_span.set_attribute("output_tokens", response.usage.get("output_tokens", 0))

# New:
llm_span.set_attribute("model", response.model)
llm_span.set_attribute("provider", response.provider)
llm_span.set_attribute("latency_ms", response.latency_ms)
llm_span.set_attribute("cost", response.cost)
llm_span.set_attribute("tool_calls", response.tool_calls)
```

### 2. Capture prompt and response content

The `rendered_prompt` variable is set during the `prompt_render` span (engine.py ~line 397-401). It is already in scope for `model_fn` because `model_fn` is a closure defined inside `Agent.run()`. Add to `model_fn`:

```python
llm_span.set_attribute("prompt", _truncate(rendered_prompt, 10_000))
llm_span.set_attribute("response", _truncate(response.content, 10_000))
```

Helper at module level:
```python
def _truncate(text: str | None, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated at {len(text)} chars]"
```

### 2b. Normalize tool_calls before storage

`CompletionResponse.tool_calls` is a `list` with no type annotation. Provider implementations may return varying shapes (e.g., OpenAI wraps under `function.name`/`function.arguments`). Normalize to plain dicts before storing:

```python
def _normalize_tool_calls(raw_calls: list) -> list[dict]:
    """Ensure tool_calls are plain JSON-serializable dicts."""
    normalized = []
    for tc in raw_calls:
        if isinstance(tc, dict):
            # Handle OpenAI-style nested format
            if "function" in tc:
                normalized.append({
                    "id": tc.get("id"),
                    "name": tc["function"]["name"],
                    "arguments": tc["function"].get("arguments", {}),
                })
            else:
                normalized.append(tc)
        else:
            normalized.append({"raw": str(tc)})
    return normalized
```

In `model_fn`:
```python
llm_span.set_attribute("tool_calls", _normalize_tool_calls(response.tool_calls) if response.tool_calls else [])
```

### 3. Propagate orchestration steps to the `orchestration` span

**Key constraint:** `model_fn` and `tool_fn` are closures that orchestration patterns call as callbacks. The orchestration patterns (in `patterns.py`) create `AgentStep` objects internally *after* `model_fn` returns — so `orch_step`/`observation` **cannot** be set inside `model_fn`.

**Solution:** After `self._pattern.execute()` returns in `engine.py` (line ~463-470), iterate over `result["steps"]` and attach them as events on the `orch_span`:

```python
# In engine.py, after result = await self._pattern.execute(...)
for i, step in enumerate(result.get("steps", [])):
    step_data = {
        "iteration": i + 1,
        "pattern": self._orchestration_config.get("pattern", "react"),
    }
    if hasattr(step, "thought") and step.thought:
        step_data["thought"] = _truncate(step.thought, 5_000)
    if hasattr(step, "action") and step.action:
        step_data["action"] = step.action
        step_data["action_input"] = step.action_input or {}
    if hasattr(step, "observation") and step.observation:
        step_data["observation"] = _truncate(step.observation, 5_000)
    if hasattr(step, "result") and step.result:
        step_data["result"] = _truncate(step.result, 5_000)
    orch_span.add_event("orch_step", step_data)
```

This stores orchestration steps as **events on the `orchestration` span** rather than attributes on `llm.complete` spans. This is the correct place because:
1. `orch_span` is in scope at this point (defined at line 458)
2. Steps are naturally time-ordered events
3. Multiple steps map to multiple events (not a single attribute)

**Frontend reads:** The Overview tab and Events tab will read `orch_span.events` where `event.name === "orch_step"` to display the thought/action/observation chain.

### 4. Capture guardrail results as span events

**Current status:** `self._guardrails` is stored on `Agent` (line 370) but never invoked in `Agent.run()`. Guardrail execution is not yet wired into the pipeline. The Guardrails tab will be grayed out until this pipeline stage is implemented.

**When guardrails are wired in**, use `span.add_event()` on the `root_span`:

```python
root_span.add_event("guardrail", {
    "guardrail_name": guardrail.name,
    "guardrail_type": "input" or "output",
    "action": "pass" or "redact" or "block",
    "details": details_dict,
})
```

This uses the existing `Span.add_event()` method (tracing.py line 32-39) which appends to the `events` list with a timestamp. The frontend chip derivation checks `events` array for `name === "guardrail"`, which correctly handles this.

### 5. Enrich tool spans

For `tool.call` spans, capture input and output:

```python
tool_span.set_attribute("tool_args", tool_arguments)
tool_span.set_attribute("tool_result", _truncate(str(tool_result), 5_000))
```

Note: `tool_args` matches the existing key name that `SpanNode.tsx` already tries to read from `attrs.tool_args`.

### 6. Capture errors

In any span's error handler:

```python
span.set_attribute("error_message", str(exc))
```

## Frontend Changes Required

### Fix Existing Attribute Reads (Bug Fix)

Before adding new features, fix `SpanNode.tsx` and `TraceTimeline.tsx` to read flat attributes:

**TraceTimeline.tsx** — token calculation:
```typescript
// Before (broken — reads nested metadata.usage):
const meta = s.attributes.metadata as Record<string, unknown>;
const usage = meta?.usage as { prompt_tokens?: number };
return acc + (usage?.prompt_tokens ?? 0);

// After (reads flat attributes):
const attrs = s.attributes;
return acc + ((attrs.input_tokens as number) ?? 0);
```

**SpanNode.tsx** — attribute reads:
```typescript
// Before (broken — reads nested metadata):
const meta = attrs.metadata as Record<string, unknown>;
const model = meta?.model as string;

// After (reads flat attributes):
const model = attrs.model as string;
const provider = attrs.provider as string;
const prompt = attrs.prompt as string;
const response = attrs.response as string;
const toolArgs = attrs.tool_args;
const toolResult = attrs.tool_result;
```

### New Components

All in `src/components/console/`:

1. **`SpanDetailPanel.tsx`** — Container with span header, tab bar, and content area. Receives `selectedSpan: SpanTreeNode | null` and `activeTab: string`. Renders the appropriate tab component.

2. **`SpanOverviewTab.tsx`** — Metrics grid (model, provider, latency, cost), token bar, orchestration step visualization, response preview, error display.

3. **`SpanInputTab.tsx`** — Renders `attributes.prompt` as preformatted text with word-wrap.

4. **`SpanOutputTab.tsx`** — Renders `attributes.response` as preformatted text.

5. **`SpanToolCallsTab.tsx`** — For `llm.complete` spans: renders `attributes.tool_calls` as formatted JSON cards. For `tool.call` spans: renders `attributes.tool` (name), `attributes.tool_args` (input), `attributes.tool_result` (output).

6. **`SpanGuardrailsTab.tsx`** — Filters `span.events` for `name === "guardrail"` and renders each as a card with guardrail_name, type, action, details.

7. **`SpanEventsTab.tsx`** — Renders all `span.events` chronologically. Each event shows relative timestamp (ms from span start), event name, and attributes as expandable JSON.

8. **`SpanRawTab.tsx`** — Renders `JSON.stringify(span, null, 2)` in a `<pre>` block with a copy-to-clipboard button.

9. **`SpanChips.tsx`** — Pure component: given a `SpanTreeNode`, returns chip badges based on derivation rules. Each chip has an `onClick` that calls `onChipClick(tabName)`.

### Modified Components

1. **`ConsoleRightPanel.tsx`** — Becomes the layout owner for the vertical split. Renders `<TraceTimeline>` in the top section and `<SpanDetailPanel>` in the bottom section, separated by a draggable divider. The panel keeps its existing fixed width (`w-[340px]`). Default split: 60% timeline / 40% detail. Split position persisted in `localStorage` key `astromesh:detail-panel-height`. When no span is selected, the detail panel shows a placeholder ("Click a span to inspect").

2. **`SpanNode.tsx`** — Removes nested `metadata` reads and fallbacks like `attrs.tool_args ?? meta?.args` (fixes bug by reading flat attributes directly). Removes the current inline expanded detail block (the `renderAttributes()` function and `expanded` state). Adds `SpanChips` rendering inline. Adds `onClick` to select span. Child expand/collapse (showing/hiding children in the tree) is **preserved** — only the inline attribute detail is removed. New props:

    ```typescript
    interface SpanNodeProps {
      node: SpanTreeNode;
      rootDuration: number;
      depth: number;
      selectedSpanId: string | null;          // NEW: highlight selected
      onSelectSpan: (spanId: string) => void; // NEW: selection callback
      onSelectTab: (tab: string) => void;     // NEW: chip click → tab
    }
    ```

3. **`TraceTimeline.tsx`** — Fixes token calculation to read flat `input_tokens`/`output_tokens`. Adds total cost to header stats. No longer owns selection state (lifted to `ConsoleRightPanel`). Receives `selectedSpanId`, `onSelectSpan`, `onSelectTab` as props and passes them through to `SpanNode` children.

### State Management

State lives in **`ConsoleRightPanel.tsx`** as component-local state, since it's the parent of both `TraceTimeline` and `SpanDetailPanel`:

```typescript
const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
const [activeTab, setActiveTab] = useState<string>("overview");
```

**Component composition:**
```
ConsoleRightPanel (owns selection state + split layout)
├─ TraceTimeline (top, scrollable)
│   ├─ SpanNode (receives onSelectSpan, onSelectTab as props)
│   │   └─ SpanChips (onClick → onSelectTab)
│   └─ ...more SpanNodes
├─ DragHandle (resize divider)
└─ SpanDetailPanel (bottom, receives selectedSpan + activeTab)
    ├─ SpanOverviewTab
    ├─ SpanInputTab
    ├─ SpanOutputTab
    ├─ SpanToolCallsTab
    ├─ SpanGuardrailsTab
    ├─ SpanEventsTab
    └─ SpanRawTab
```

When a span is clicked, `SpanNode` calls `onSelectSpan(spanId)`. When a chip is clicked, `SpanNode` calls both `onSelectSpan(spanId)` and `onSelectTab(tabForChip)`. `ConsoleRightPanel` resolves `selectedSpanId` to the full `SpanTreeNode` from the trace data and passes it to `SpanDetailPanel`.

### Type Updates (`src/types/console.ts`)

Replace the loose `Record<string, unknown>` attributes with a typed interface:

```typescript
export interface SpanAttributes {
  // Identity
  agent?: string;
  session?: string;

  // LLM
  model?: string;
  provider?: string;
  input_tokens?: number;
  output_tokens?: number;
  latency_ms?: number;
  cost?: number;
  prompt?: string;
  response?: string;
  tool_calls?: Array<{ id?: string; name: string; arguments: Record<string, unknown> }>;

  // Tool
  tool?: string;
  tool_args?: Record<string, unknown>;
  tool_result?: string;

  // Orchestration (pattern name only — steps are in span.events)
  pattern?: string;

  // Error
  error_message?: string;

  // Catch-all for unknown attributes
  [key: string]: unknown;
}

export interface TraceSpan {
  name: string;
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  status: "ok" | "error" | "unset";
  attributes: SpanAttributes;
  events: Array<{
    name: string;
    timestamp: number;
    attributes: Record<string, unknown>;
  }>;
  start_time: number;
  end_time: number | null;
  duration_ms: number | null;
}
```

## Scope Boundaries

**In scope:**
- All frontend components listed above (9 new, 3 modified)
- Backend span enrichment (6 changes)
- Fix existing attribute read bug in SpanNode + TraceTimeline
- Resizable split panel with localStorage persistence
- Tab navigation with disabled state for empty tabs
- Chip indicators with click-to-tab
- Truncation for large text fields

**Out of scope:**
- Real-time WebSocket streaming of spans (future enhancement)
- Search/filter within trace data
- Export trace data
- Comparison view updates (existing CompareView unchanged)
- Full-text lazy loading (deferred — truncation is sufficient for v1)
