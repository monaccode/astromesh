# Trace Timeline Detail Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add detailed debugging visibility to the Trace Timeline by enriching backend span data and building a split-panel UI with tabbed detail view.

**Architecture:** Backend enriches spans with model/provider/latency/cost/prompt/response/tool data and orchestration events. Frontend fixes flat-attribute reads, adds chip indicators to spans, and renders a resizable split panel with 7 tabs (Overview, Input, Output, Tool Calls, Guardrails, Events, Raw).

**Tech Stack:** Python 3.12 (backend), React + TypeScript + Tailwind CSS (frontend), pytest (backend tests)

**Spec:** `docs/superpowers/specs/2026-03-22-trace-timeline-detail-design.md`

---

## File Map

### Backend (Python)

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `astromesh/runtime/engine.py` | Enrich spans with model/provider/latency/cost/prompt/response/tool_args/tool_result/error/orch events |
| Create | `tests/test_span_enrichment.py` | Unit tests for span enrichment logic |

### Frontend (TypeScript/React)

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `astromesh-forge/src/types/console.ts` | Add `SpanAttributes` interface, type `TraceSpan.attributes` |
| Modify | `astromesh-forge/src/components/console/TraceTimeline.tsx` | Fix token reads, add cost stat, accept selection props |
| Modify | `astromesh-forge/src/components/console/SpanNode.tsx` | Fix attribute reads, remove inline detail, add chips + selection |
| Modify | `astromesh-forge/src/components/console/ConsoleRightPanel.tsx` | Split layout, selection state, render detail panel |
| Create | `astromesh-forge/src/components/console/SpanChips.tsx` | Chip indicator badges with click-to-tab |
| Create | `astromesh-forge/src/components/console/SpanDetailPanel.tsx` | Tab bar + content container |
| Create | `astromesh-forge/src/components/console/SpanOverviewTab.tsx` | Metrics grid, tokens, orch steps, response preview |
| Create | `astromesh-forge/src/components/console/SpanInputTab.tsx` | Full prompt display |
| Create | `astromesh-forge/src/components/console/SpanOutputTab.tsx` | Full response display |
| Create | `astromesh-forge/src/components/console/SpanToolCallsTab.tsx` | Tool arguments and results |
| Create | `astromesh-forge/src/components/console/SpanGuardrailsTab.tsx` | Guardrail events display |
| Create | `astromesh-forge/src/components/console/SpanEventsTab.tsx` | All span events chronological |
| Create | `astromesh-forge/src/components/console/SpanRawTab.tsx` | JSON dump with copy button |

---

## Task 1: Backend — Add helper functions and enrich `llm.complete` spans

**Files:**
- Modify: `astromesh/runtime/engine.py:1-10` (add helpers at module top)
- Modify: `astromesh/runtime/engine.py:424-442` (enrich `model_fn`)
- Create: `tests/test_span_enrichment.py`

- [ ] **Step 1: Write test for `_truncate` helper**

Create `tests/test_span_enrichment.py`:

```python
from astromesh.runtime.engine import _truncate


def test_truncate_none():
    assert _truncate(None, 100) == ""


def test_truncate_empty():
    assert _truncate("", 100) == ""


def test_truncate_within_limit():
    assert _truncate("hello", 100) == "hello"


def test_truncate_at_limit():
    text = "a" * 100
    assert _truncate(text, 100) == text


def test_truncate_over_limit():
    text = "a" * 200
    result = _truncate(text, 100)
    assert len(result) > 100
    assert result.startswith("a" * 100)
    assert "[truncated at 200 chars]" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/monaccode/astromesh && uv run pytest tests/test_span_enrichment.py -v`
Expected: FAIL — `_truncate` not importable

- [ ] **Step 3: Implement `_truncate` and `_normalize_tool_calls` in engine.py**

Add at module level in `astromesh/runtime/engine.py` (after existing imports, before class definitions):

```python
def _truncate(text: str | None, limit: int) -> str:
    """Truncate text to limit chars, appending a marker if truncated."""
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated at {len(text)} chars]"


def _parse_args(args):
    """Parse arguments that may be a JSON string (OpenAI) or already a dict."""
    if isinstance(args, str):
        try:
            return json.loads(args)
        except (json.JSONDecodeError, ValueError):
            return {"_raw": args}
    return args


def _normalize_tool_calls(raw_calls: list) -> list[dict]:
    """Normalize tool_calls to plain JSON-serializable dicts."""
    normalized = []
    for tc in raw_calls:
        if isinstance(tc, dict):
            if "function" in tc:
                normalized.append({
                    "id": tc.get("id"),
                    "name": tc["function"]["name"],
                    "arguments": _parse_args(tc["function"].get("arguments", {})),
                })
            else:
                normalized.append(tc)
        else:
            normalized.append({"raw": str(tc)})
    return normalized
```

- [ ] **Step 4: Run test to verify `_truncate` passes**

Run: `cd D:/monaccode/astromesh && uv run pytest tests/test_span_enrichment.py -v`
Expected: PASS

- [ ] **Step 5: Write test for `_normalize_tool_calls`**

Append to `tests/test_span_enrichment.py`:

```python
from astromesh.runtime.engine import _normalize_tool_calls


def test_normalize_flat_dict():
    raw = [{"id": "1", "name": "search", "arguments": {"q": "test"}}]
    assert _normalize_tool_calls(raw) == raw


def test_normalize_openai_nested():
    raw = [{"id": "call_1", "function": {"name": "search", "arguments": {"q": "test"}}}]
    result = _normalize_tool_calls(raw)
    assert result == [{"id": "call_1", "name": "search", "arguments": {"q": "test"}}]


def test_normalize_empty():
    assert _normalize_tool_calls([]) == []


def test_normalize_non_dict():
    result = _normalize_tool_calls(["not_a_dict"])
    assert result == [{"raw": "not_a_dict"}]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd D:/monaccode/astromesh && uv run pytest tests/test_span_enrichment.py -v`
Expected: PASS

- [ ] **Step 7: Enrich `model_fn` in engine.py**

In `engine.py`, inside `model_fn` (line ~431-437), add after the existing `output_tokens` set_attribute:

```python
                    llm_span.set_attribute("model", response.model)
                    llm_span.set_attribute("provider", response.provider)
                    llm_span.set_attribute("latency_ms", response.latency_ms)
                    llm_span.set_attribute("cost", response.cost)
                    llm_span.set_attribute(
                        "tool_calls",
                        _normalize_tool_calls(response.tool_calls) if response.tool_calls else [],
                    )
                    llm_span.set_attribute("prompt", _truncate(rendered_prompt, 10_000))
                    llm_span.set_attribute("response", _truncate(response.content, 10_000))
```

Also in the `except` block (line ~440-441), add before `raise`:

```python
                    llm_span.set_attribute("error_message", str(e))
```

Change `except Exception:` to `except Exception as e:`.

- [ ] **Step 8: Enrich `tool_fn` in engine.py**

In `engine.py`, inside `tool_fn` (line ~444-456), add after tool execution succeeds:

```python
                    tool_span.set_attribute("tool_args", args)
                    tool_span.set_attribute("tool_result", _truncate(str(observation), 5_000))
```

Also in the `except` block, add before `raise`:

```python
                    tool_span.set_attribute("error_message", str(e))
```

Change `except Exception:` to `except Exception as e:`.

- [ ] **Step 9: Add orchestration step events**

In `engine.py`, after `result = await self._pattern.execute(...)` (line ~463-470) and BEFORE `tracing.finish_span(orch_span)`:

```python
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

- [ ] **Step 10: Add error capture on root_span**

In `engine.py`, in the outer `except Exception:` block (line ~514-516), add before `raise`:

```python
            root_span.set_attribute("error_message", str(e))
```

Change `except Exception:` to `except Exception as e:`.

- [ ] **Step 11: Run existing tests**

Run: `cd D:/monaccode/astromesh && uv run pytest tests/test_engine.py tests/test_span_enrichment.py -v`
Expected: PASS

- [ ] **Step 12: Lint**

Run: `cd D:/monaccode/astromesh && uv run ruff check astromesh/runtime/engine.py tests/test_span_enrichment.py && uv run ruff format astromesh/runtime/engine.py tests/test_span_enrichment.py`

- [ ] **Step 13: Commit**

```bash
cd D:/monaccode/astromesh
git add astromesh/runtime/engine.py tests/test_span_enrichment.py
git commit -m "feat(tracing): enrich spans with model/provider/latency/cost/prompt/response/tools/orch"
```

---

## Task 2: Frontend — Update types and fix attribute reads

**Files:**
- Modify: `astromesh-forge/src/types/console.ts:1-16`
- Modify: `astromesh-forge/src/components/console/TraceTimeline.tsx:20-30`
- Modify: `astromesh-forge/src/components/console/SpanNode.tsx:129-226`

- [ ] **Step 1: Add `SpanAttributes` interface to `console.ts`**

Replace lines 1-16 of `astromesh-forge/src/types/console.ts` with:

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

  // Orchestration (steps are in span.events)
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

Keep lines 17+ (Trace, RunResponse, etc.) unchanged.

- [ ] **Step 2: Fix TraceTimeline.tsx token reads**

Replace lines 20-30 of `TraceTimeline.tsx` with:

```typescript
  const totalTokensIn = trace.spans.reduce(
    (acc, s) => acc + ((s.attributes.input_tokens as number) ?? 0),
    0,
  );

  const totalTokensOut = trace.spans.reduce(
    (acc, s) => acc + ((s.attributes.output_tokens as number) ?? 0),
    0,
  );

  const totalCost = trace.spans.reduce(
    (acc, s) => acc + ((s.attributes.cost as number) ?? 0),
    0,
  );
```

Also update the header (line ~42-46) to show cost:

```typescript
        {totalCost > 0 && (
          <span className="text-gray-500 ml-2">
            ${totalCost.toFixed(4)}
          </span>
        )}
```

- [ ] **Step 3: Verify the app compiles**

Run: `cd D:/monaccode/astromesh/astromesh-forge && npm run build`
Expected: Compiles. `SpanNode` still uses `metadata` reads but the type change is backward-compatible (index signature `[key: string]: unknown` allows any key).

- [ ] **Step 4: Commit**

```bash
cd D:/monaccode/astromesh
git add astromesh-forge/src/types/console.ts astromesh-forge/src/components/console/TraceTimeline.tsx
git commit -m "fix(forge): type SpanAttributes and fix flat attribute reads in timeline"
```

---

## Task 3: Frontend — Create SpanChips component

**Files:**
- Create: `astromesh-forge/src/components/console/SpanChips.tsx`

- [ ] **Step 1: Create `SpanChips.tsx`**

```typescript
import type { SpanTreeNode } from "../../utils/trace-tree";

interface SpanChipsProps {
  node: SpanTreeNode;
  onChipClick: (tab: string) => void;
}

interface ChipDef {
  label: string;
  tab: string;
  show: boolean;
  color: string;
}

export function SpanChips({ node, onChipClick }: SpanChipsProps) {
  const attrs = node.attributes;
  const chips: ChipDef[] = [
    {
      label: "\u{1F4AC}",
      tab: "output",
      show: typeof attrs.response === "string" && attrs.response.length > 0,
      color: "bg-amber-500/20 text-amber-400",
    },
    {
      label: "\u{1F527}",
      tab: "toolcalls",
      show: Array.isArray(attrs.tool_calls) && attrs.tool_calls.length > 0,
      color: "bg-orange-500/20 text-orange-400",
    },
    {
      label: "\u2705",
      tab: "output",
      show: node.name.startsWith("tool.") && node.status === "ok",
      color: "bg-green-500/20 text-green-400",
    },
    {
      label: "\u{1F4CB}",
      tab: "events",
      show: node.events.length > 0,
      color: "bg-blue-500/20 text-blue-400",
    },
    {
      label: "\u26A0\uFE0F",
      tab: "overview",
      show: node.status === "error",
      color: "bg-red-500/20 text-red-400",
    },
    {
      label: "\u{1F6E1}\uFE0F",
      tab: "guardrails",
      show: node.events.some((e) => e.name === "guardrail"),
      color: "bg-purple-500/20 text-purple-400",
    },
  ];

  const visible = chips.filter((c) => c.show);
  if (visible.length === 0) return null;

  return (
    <span className="inline-flex gap-0.5 ml-1">
      {visible.map((chip, i) => (
        <span
          key={i}
          className={`${chip.color} text-[8px] px-1 rounded cursor-pointer hover:opacity-80`}
          title={`View ${chip.tab}`}
          onClick={(e) => {
            e.stopPropagation();
            onChipClick(chip.tab);
          }}
        >
          {chip.label}
        </span>
      ))}
    </span>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd D:/monaccode/astromesh/astromesh-forge && npm run build`
Expected: Compiles (unused component warning is fine)

- [ ] **Step 3: Commit**

```bash
cd D:/monaccode/astromesh
git add astromesh-forge/src/components/console/SpanChips.tsx
git commit -m "feat(forge): add SpanChips component for trace span indicators"
```

---

## Task 4: Frontend — Rework SpanNode, TraceTimeline, ConsoleRightPanel, and SpanDetailPanel

> **Important:** Tasks 4, 5, and 6 from the original plan are merged here to avoid broken intermediate builds. SpanNode, TraceTimeline, and ConsoleRightPanel must be updated together since they share new props.

**Files:**
- Modify: `astromesh-forge/src/components/console/SpanNode.tsx`
- Modify: `astromesh-forge/src/components/console/TraceTimeline.tsx`
- Modify: `astromesh-forge/src/components/console/ConsoleRightPanel.tsx`
- Create: `astromesh-forge/src/components/console/SpanDetailPanel.tsx`

- [ ] **Step 1: Rewrite SpanNode.tsx**

Replace the full content of `SpanNode.tsx` with:

```typescript
import { useState } from "react";
import {
  Bot,
  Brain,
  Wrench,
  Shield,
  Database,
  ChevronDown,
  ChevronRight,
  FileText,
} from "lucide-react";
import type { SpanTreeNode } from "../../utils/trace-tree";
import { getSpanColor, getSpanDotColor } from "../../utils/trace-tree";
import { SpanChips } from "./SpanChips";

const SPAN_ICONS: Array<[string, typeof Bot]> = [
  ["agent", Bot],
  ["llm", Brain],
  ["model", Brain],
  ["tool", Wrench],
  ["guardrail", Shield],
  ["memory", Database],
  ["prompt", FileText],
  ["orchestration", Brain],
];

function getSpanIcon(name: string) {
  const lower = name.toLowerCase();
  for (const [prefix, icon] of SPAN_ICONS) {
    if (lower.startsWith(prefix)) return icon;
  }
  return null;
}

export interface SpanNodeProps {
  node: SpanTreeNode;
  rootDuration: number;
  depth?: number;
  selectedSpanId: string | null;
  onSelectSpan: (spanId: string) => void;
  onSelectTab: (tab: string) => void;
}

export function SpanNode({
  node,
  rootDuration,
  depth = 0,
  selectedSpanId,
  onSelectSpan,
  onSelectTab,
}: SpanNodeProps) {
  const [childrenExpanded, setChildrenExpanded] = useState(depth === 0);
  const hasChildren = node.children.length > 0;
  const isSelected = node.span_id === selectedSpanId;

  const duration = node.duration_ms ?? 0;
  const barWidth = rootDuration > 0 ? (duration / rootDuration) * 100 : 0;
  const isError = node.status === "error";
  const SpanIcon = getSpanIcon(node.name);

  const handleClick = () => {
    onSelectSpan(node.span_id);
  };

  const handleChevronClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setChildrenExpanded(!childrenExpanded);
  };

  const handleChipClick = (tab: string) => {
    onSelectSpan(node.span_id);
    onSelectTab(tab);
  };

  return (
    <div style={{ marginLeft: depth > 0 ? 14 : 0 }}>
      <div
        className={`bg-gray-800 rounded px-2 py-1.5 border-l-[3px] ${
          isError ? "border-red-500" : getSpanColor(node.name)
        } cursor-pointer mb-0.5 ${isSelected ? "ring-1 ring-cyan-500/50 bg-gray-750" : ""}`}
        onClick={handleClick}
      >
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-1.5 min-w-0">
            {hasChildren && (
              <span
                className={getSpanDotColor(node.name)}
                onClick={handleChevronClick}
              >
                {childrenExpanded ? (
                  <ChevronDown size={10} />
                ) : (
                  <ChevronRight size={10} />
                )}
              </span>
            )}
            {SpanIcon && (
              <SpanIcon size={10} className={getSpanDotColor(node.name)} />
            )}
            <span
              className={`text-[10px] truncate ${
                isError
                  ? "text-red-400"
                  : depth === 0
                    ? "text-gray-100 font-semibold"
                    : "text-gray-300"
              }`}
            >
              {node.name}
            </span>
            <SpanChips node={node} onChipClick={handleChipClick} />
            {node.status === "ok" && (
              <span className="bg-green-500/20 text-green-400 text-[8px] px-1 rounded">
                OK
              </span>
            )}
            {isError && (
              <span className="bg-red-500/20 text-red-400 text-[8px] px-1 rounded">
                ERR
              </span>
            )}
          </div>
          <span className="text-[10px] text-gray-500 font-mono flex-shrink-0 ml-2">
            {duration}ms
          </span>
        </div>

        {barWidth > 0 && (
          <div className="mt-1 bg-gray-900 rounded-sm h-[3px]">
            <div
              className={`h-full rounded-sm opacity-50 ${
                isError ? "bg-red-500" : "bg-cyan-500"
              }`}
              style={{ width: `${Math.max(barWidth, 1)}%` }}
            />
          </div>
        )}
      </div>

      {childrenExpanded &&
        node.children.map((child) => (
          <SpanNode
            key={child.span_id}
            node={child}
            rootDuration={rootDuration}
            depth={depth + 1}
            selectedSpanId={selectedSpanId}
            onSelectSpan={onSelectSpan}
            onSelectTab={onSelectTab}
          />
        ))}
    </div>
  );
}
```

- [ ] **Step 2: Update TraceTimeline.tsx to accept and pass selection props**

Replace the full content of `TraceTimeline.tsx`:

```typescript
import type { Trace } from "../../types/console";
import { buildSpanTree } from "../../utils/trace-tree";
import { SpanNode } from "./SpanNode";

interface TraceTimelineProps {
  trace: Trace;
  label?: string;
  accentColor?: string;
  selectedSpanId: string | null;
  onSelectSpan: (spanId: string) => void;
  onSelectTab: (tab: string) => void;
}

export function TraceTimeline({
  trace,
  label,
  accentColor = "text-cyan-400",
  selectedSpanId,
  onSelectSpan,
  onSelectTab,
}: TraceTimelineProps) {
  const tree = buildSpanTree(trace.spans);
  const rootDuration = tree.length > 0 ? (tree[0].duration_ms ?? 0) : 0;

  const totalTokensIn = trace.spans.reduce(
    (acc, s) => acc + ((s.attributes.input_tokens as number) ?? 0),
    0,
  );

  const totalTokensOut = trace.spans.reduce(
    (acc, s) => acc + ((s.attributes.output_tokens as number) ?? 0),
    0,
  );

  const totalCost = trace.spans.reduce(
    (acc, s) => acc + ((s.attributes.cost as number) ?? 0),
    0,
  );

  return (
    <div className="flex flex-col gap-1">
      <div className={`text-[10px] ${accentColor} mb-1`}>
        {label && <span className="font-semibold mr-2">{label}</span>}
        trace: {trace.trace_id.slice(0, 8)}
        {rootDuration > 0 && (
          <span className="text-gray-500 ml-2">
            {(rootDuration / 1000).toFixed(1)}s total
          </span>
        )}
        {(totalTokensIn > 0 || totalTokensOut > 0) && (
          <span className="text-gray-500 ml-2">
            {totalTokensIn + totalTokensOut} tokens
          </span>
        )}
        {totalCost > 0 && (
          <span className="text-gray-500 ml-2">${totalCost.toFixed(4)}</span>
        )}
      </div>

      {tree.map((node) => (
        <SpanNode
          key={node.span_id}
          node={node}
          rootDuration={rootDuration}
          selectedSpanId={selectedSpanId}
          onSelectSpan={onSelectSpan}
          onSelectTab={onSelectTab}
        />
      ))}

      {tree.length === 0 && (
        <div className="text-gray-600 text-xs text-center py-4">
          No spans in this trace
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit SpanNode and TraceTimeline** (do NOT build yet — ConsoleRightPanel still needs updating)

```bash
cd D:/monaccode/astromesh
git add astromesh-forge/src/components/console/SpanNode.tsx astromesh-forge/src/components/console/TraceTimeline.tsx
```

(We'll commit everything together at the end of this task.)

- [ ] **Step 4: Create all 7 detail tab components**

Create the following files. These are self-contained components with no cross-dependencies:

### Task 4b: Create detail panel tab components

**Files:**
- Create: `astromesh-forge/src/components/console/SpanOverviewTab.tsx`
- Create: `astromesh-forge/src/components/console/SpanInputTab.tsx`
- Create: `astromesh-forge/src/components/console/SpanOutputTab.tsx`
- Create: `astromesh-forge/src/components/console/SpanToolCallsTab.tsx`
- Create: `astromesh-forge/src/components/console/SpanGuardrailsTab.tsx`
- Create: `astromesh-forge/src/components/console/SpanEventsTab.tsx`
- Create: `astromesh-forge/src/components/console/SpanRawTab.tsx`

- [ ] **Step 1: Create `SpanOverviewTab.tsx`**

```typescript
import type { SpanTreeNode } from "../../utils/trace-tree";

interface SpanOverviewTabProps {
  node: SpanTreeNode;
  onSwitchTab: (tab: string) => void;
}

export function SpanOverviewTab({ node, onSwitchTab }: SpanOverviewTabProps) {
  const a = node.attributes;
  const hasMetrics = a.model || a.provider || a.latency_ms != null || a.cost != null;
  const hasTokens = a.input_tokens != null || a.output_tokens != null;
  const orchSteps = node.events.filter((e) => e.name === "orch_step");
  const hasResponse = typeof a.response === "string" && a.response.length > 0;
  const isError = node.status === "error";

  return (
    <div className="flex flex-col gap-3 p-3 text-[11px]">
      {/* Metrics grid */}
      {hasMetrics && (
        <div className="grid grid-cols-2 gap-2">
          {a.model && (
            <div className="bg-gray-800 rounded p-2">
              <div className="text-gray-500 text-[9px] uppercase mb-0.5">Model</div>
              <div className="text-amber-400">{a.model}</div>
            </div>
          )}
          {a.provider && (
            <div className="bg-gray-800 rounded p-2">
              <div className="text-gray-500 text-[9px] uppercase mb-0.5">Provider</div>
              <div className="text-amber-400">{a.provider}</div>
            </div>
          )}
          {a.latency_ms != null && (
            <div className="bg-gray-800 rounded p-2">
              <div className="text-gray-500 text-[9px] uppercase mb-0.5">Latency</div>
              <div className="text-orange-400">{Math.round(a.latency_ms)}ms</div>
            </div>
          )}
          {a.cost != null && (
            <div className="bg-gray-800 rounded p-2">
              <div className="text-gray-500 text-[9px] uppercase mb-0.5">Cost</div>
              <div className="text-green-400">${a.cost.toFixed(4)}</div>
            </div>
          )}
        </div>
      )}

      {/* Token usage */}
      {hasTokens && (
        <div className="bg-gray-800 rounded p-2 flex gap-4">
          {a.input_tokens != null && (
            <div>
              <span className="text-cyan-400 font-semibold text-sm">{a.input_tokens}</span>
              <span className="text-gray-500 ml-1">input</span>
            </div>
          )}
          {a.output_tokens != null && (
            <div>
              <span className="text-amber-400 font-semibold text-sm">{a.output_tokens}</span>
              <span className="text-gray-500 ml-1">output</span>
            </div>
          )}
          {a.input_tokens != null && a.output_tokens != null && (
            <div>
              <span className="text-gray-200 font-semibold text-sm">
                {a.input_tokens + a.output_tokens}
              </span>
              <span className="text-gray-500 ml-1">total</span>
            </div>
          )}
        </div>
      )}

      {/* Orchestration steps */}
      {orchSteps.length > 0 && (
        <div className="bg-gray-800 rounded p-2">
          <div className="text-gray-500 text-[9px] uppercase mb-2">
            Orchestration — {orchSteps[0].attributes.pattern} ({orchSteps.length} steps)
          </div>
          <div className="flex flex-col gap-2">
            {orchSteps.map((event, i) => {
              const ea = event.attributes;
              return (
                <div key={i} className="flex flex-col gap-1">
                  <div className="text-gray-500 text-[9px]">Step {ea.iteration as number}</div>
                  {ea.thought && (
                    <div className="border-l-2 border-purple-400 pl-2 bg-purple-400/5 rounded-r py-1">
                      <span className="text-purple-400 text-[9px] font-semibold">THOUGHT</span>
                      <div className="text-gray-300 text-[10px] mt-0.5">{ea.thought as string}</div>
                    </div>
                  )}
                  {ea.action && (
                    <div className="border-l-2 border-orange-400 pl-2 bg-orange-400/5 rounded-r py-1">
                      <span className="text-orange-400 text-[9px] font-semibold">ACTION</span>
                      <div className="text-gray-300 text-[10px] mt-0.5">{ea.action as string}</div>
                      {ea.action_input && (
                        <pre className="text-green-400 text-[9px] mt-0.5 overflow-x-auto">
                          {JSON.stringify(ea.action_input, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                  {ea.observation && (
                    <div className="border-l-2 border-blue-400 pl-2 bg-blue-400/5 rounded-r py-1">
                      <span className="text-blue-400 text-[9px] font-semibold">OBSERVATION</span>
                      <div className="text-gray-300 text-[10px] mt-0.5 break-all">
                        {ea.observation as string}
                      </div>
                    </div>
                  )}
                  {ea.result && (
                    <div className="border-l-2 border-green-400 pl-2 bg-green-400/5 rounded-r py-1">
                      <span className="text-green-400 text-[9px] font-semibold">RESULT</span>
                      <div className="text-gray-300 text-[10px] mt-0.5">{ea.result as string}</div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Response preview */}
      {hasResponse && (
        <div className="bg-gray-800 rounded p-2">
          <div className="text-gray-500 text-[9px] uppercase mb-0.5">Response Preview</div>
          <div className="text-gray-300 text-[10px] line-clamp-3">
            {a.response!.slice(0, 200)}
            {a.response!.length > 200 && "..."}
          </div>
          <button
            className="text-cyan-400 text-[9px] mt-1 hover:underline"
            onClick={() => onSwitchTab("output")}
          >
            View full response
          </button>
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="bg-red-500/10 border border-red-500/30 rounded p-2">
          <div className="text-red-400 text-[9px] uppercase mb-0.5">Error</div>
          <div className="text-red-300 text-[10px] font-mono">
            {(a.error_message as string) ?? "Unknown error"}
          </div>
        </div>
      )}

      {/* Tool info (for tool.call spans) */}
      {a.tool && (
        <div className="bg-gray-800 rounded p-2">
          <div className="text-gray-500 text-[9px] uppercase mb-0.5">Tool</div>
          <div className="text-orange-400">{a.tool}</div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create `SpanInputTab.tsx`**

```typescript
import type { SpanTreeNode } from "../../utils/trace-tree";

export function SpanInputTab({ node }: { node: SpanTreeNode }) {
  const prompt = node.attributes.prompt;
  if (!prompt) {
    return (
      <div className="text-gray-600 text-xs text-center py-8">
        No prompt data available for this span
      </div>
    );
  }

  return (
    <div className="p-3">
      <pre className="text-gray-300 bg-gray-800 rounded p-3 text-[10px] whitespace-pre-wrap break-words overflow-y-auto max-h-[400px]">
        {prompt as string}
      </pre>
    </div>
  );
}
```

- [ ] **Step 3: Create `SpanOutputTab.tsx`**

```typescript
import type { SpanTreeNode } from "../../utils/trace-tree";

export function SpanOutputTab({ node }: { node: SpanTreeNode }) {
  const response = node.attributes.response;
  const toolResult = node.attributes.tool_result;
  const content = response ?? toolResult;

  if (!content) {
    return (
      <div className="text-gray-600 text-xs text-center py-8">
        No output data available for this span
      </div>
    );
  }

  return (
    <div className="p-3">
      <pre className="text-gray-300 bg-gray-800 rounded p-3 text-[10px] whitespace-pre-wrap break-words overflow-y-auto max-h-[400px]">
        {content as string}
      </pre>
    </div>
  );
}
```

- [ ] **Step 4: Create `SpanToolCallsTab.tsx`**

```typescript
import type { SpanTreeNode } from "../../utils/trace-tree";

export function SpanToolCallsTab({ node }: { node: SpanTreeNode }) {
  const a = node.attributes;
  const toolCalls = a.tool_calls as
    | Array<{ id?: string; name: string; arguments: Record<string, unknown> }>
    | undefined;
  const isToolSpan = node.name.startsWith("tool.");

  if (!toolCalls?.length && !isToolSpan) {
    return (
      <div className="text-gray-600 text-xs text-center py-8">
        No tool call data available for this span
      </div>
    );
  }

  return (
    <div className="p-3 flex flex-col gap-3 text-[11px]">
      {/* LLM tool_calls */}
      {toolCalls?.map((tc, i) => (
        <div key={i} className="bg-gray-800 rounded p-2">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-orange-400 font-semibold">{tc.name}</span>
            {tc.id && <span className="text-gray-600 text-[9px]">{tc.id}</span>}
          </div>
          <pre className="text-green-400 bg-gray-900 rounded p-2 text-[9px] overflow-x-auto">
            {JSON.stringify(tc.arguments, null, 2)}
          </pre>
        </div>
      ))}

      {/* Tool span details */}
      {isToolSpan && (
        <div className="bg-gray-800 rounded p-2">
          <div className="text-orange-400 font-semibold mb-1">{a.tool as string}</div>
          {a.tool_args && (
            <div className="mb-2">
              <div className="text-gray-500 text-[9px] uppercase mb-0.5">Arguments</div>
              <pre className="text-green-400 bg-gray-900 rounded p-2 text-[9px] overflow-x-auto">
                {JSON.stringify(a.tool_args, null, 2)}
              </pre>
            </div>
          )}
          {a.tool_result && (
            <div>
              <div className="text-gray-500 text-[9px] uppercase mb-0.5">Result</div>
              <pre className="text-gray-300 bg-gray-900 rounded p-2 text-[9px] overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto">
                {a.tool_result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Create `SpanGuardrailsTab.tsx`**

```typescript
import type { SpanTreeNode } from "../../utils/trace-tree";

export function SpanGuardrailsTab({ node }: { node: SpanTreeNode }) {
  const guardrailEvents = node.events.filter((e) => e.name === "guardrail");

  if (guardrailEvents.length === 0) {
    return (
      <div className="text-gray-600 text-xs text-center py-8">
        No guardrail events for this span
      </div>
    );
  }

  return (
    <div className="p-3 flex flex-col gap-2 text-[11px]">
      {guardrailEvents.map((event, i) => {
        const ea = event.attributes;
        const action = ea.action as string;
        const actionColor =
          action === "block"
            ? "text-red-400"
            : action === "redact"
              ? "text-amber-400"
              : "text-green-400";

        return (
          <div key={i} className="bg-gray-800 rounded p-2">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-purple-400 font-semibold">
                {ea.guardrail_name as string}
              </span>
              <span className="text-gray-500 text-[9px] uppercase">
                {ea.guardrail_type as string}
              </span>
              <span className={`${actionColor} text-[9px] font-semibold uppercase`}>
                {action}
              </span>
            </div>
            {ea.details && (
              <pre className="text-gray-400 bg-gray-900 rounded p-2 text-[9px] overflow-x-auto">
                {JSON.stringify(ea.details, null, 2)}
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 6: Create `SpanEventsTab.tsx`**

```typescript
import type { SpanTreeNode } from "../../utils/trace-tree";

export function SpanEventsTab({ node }: { node: SpanTreeNode }) {
  if (node.events.length === 0) {
    return (
      <div className="text-gray-600 text-xs text-center py-8">
        No events for this span
      </div>
    );
  }

  const spanStart = node.start_time;

  return (
    <div className="p-3 flex flex-col gap-1.5 text-[11px]">
      {node.events.map((event, i) => {
        const relativeMs = Math.round((event.timestamp - spanStart) * 1000);
        return (
          <div key={i} className="bg-gray-800 rounded p-2">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-gray-500 font-mono text-[9px] w-14 text-right flex-shrink-0">
                +{relativeMs}ms
              </span>
              <span className="text-cyan-400 font-semibold">{event.name}</span>
            </div>
            {Object.keys(event.attributes).length > 0 && (
              <pre className="text-gray-400 bg-gray-900 rounded p-2 text-[9px] overflow-x-auto ml-16">
                {JSON.stringify(event.attributes, null, 2)}
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 7: Create `SpanRawTab.tsx`**

```typescript
import { useState } from "react";
import { Copy, Check } from "lucide-react";
import type { SpanTreeNode } from "../../utils/trace-tree";

export function SpanRawTab({ node }: { node: SpanTreeNode }) {
  const [copied, setCopied] = useState(false);

  const raw = JSON.stringify(
    { attributes: node.attributes, events: node.events },
    null,
    2,
  );

  const handleCopy = async () => {
    await navigator.clipboard.writeText(raw);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="p-3">
      <div className="flex justify-end mb-1">
        <button
          className="flex items-center gap-1 text-gray-400 hover:text-gray-200 text-[10px]"
          onClick={handleCopy}
        >
          {copied ? <Check size={10} /> : <Copy size={10} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="text-gray-400 bg-gray-800 rounded p-3 text-[9px] overflow-x-auto overflow-y-auto max-h-[400px] whitespace-pre-wrap">
        {raw}
      </pre>
    </div>
  );
}
```

### Task 4c: Create SpanDetailPanel and wire ConsoleRightPanel

- [ ] **Step 5: Create `SpanDetailPanel.tsx`**

```typescript
import type { SpanTreeNode } from "../../utils/trace-tree";
import { getSpanDotColor } from "../../utils/trace-tree";
import { SpanOverviewTab } from "./SpanOverviewTab";
import { SpanInputTab } from "./SpanInputTab";
import { SpanOutputTab } from "./SpanOutputTab";
import { SpanToolCallsTab } from "./SpanToolCallsTab";
import { SpanGuardrailsTab } from "./SpanGuardrailsTab";
import { SpanEventsTab } from "./SpanEventsTab";
import { SpanRawTab } from "./SpanRawTab";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "input", label: "Input" },
  { id: "output", label: "Output" },
  { id: "toolcalls", label: "Tool Calls" },
  { id: "guardrails", label: "Guardrails" },
  { id: "events", label: "Events" },
  { id: "raw", label: "Raw" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function tabHasData(node: SpanTreeNode, tabId: TabId): boolean {
  const a = node.attributes;
  switch (tabId) {
    case "overview":
      return true; // Always available
    case "input":
      return typeof a.prompt === "string" && a.prompt.length > 0;
    case "output":
      return (
        (typeof a.response === "string" && a.response.length > 0) ||
        (typeof a.tool_result === "string" && a.tool_result.length > 0)
      );
    case "toolcalls":
      return (
        (Array.isArray(a.tool_calls) && a.tool_calls.length > 0) ||
        node.name.startsWith("tool.")
      );
    case "guardrails":
      return node.events.some((e) => e.name === "guardrail");
    case "events":
      return node.events.length > 0;
    case "raw":
      return true; // Always available
  }
}

interface SpanDetailPanelProps {
  node: SpanTreeNode | null;
  activeTab: string;
  onTabChange: (tab: string) => void;
}

export function SpanDetailPanel({
  node,
  activeTab,
  onTabChange,
}: SpanDetailPanelProps) {
  if (!node) {
    return (
      <div className="flex items-center justify-center h-full text-gray-600 text-xs">
        Click a span to inspect
      </div>
    );
  }

  const currentTab = (activeTab as TabId) || "overview";

  return (
    <div className="flex flex-col h-full">
      {/* Span header */}
      <div className="px-3 py-1.5 bg-gray-900 border-b border-gray-800 flex items-center gap-2 text-[11px] flex-shrink-0">
        <span className={`font-semibold ${getSpanDotColor(node.name)}`}>
          {node.name}
        </span>
        <span className="text-gray-600">{node.span_id.slice(0, 8)}</span>
        <span className="text-gray-600">{node.duration_ms ?? 0}ms</span>
        {node.attributes.model && (
          <span className="text-gray-500">
            {node.attributes.model as string} via{" "}
            {node.attributes.provider as string}
          </span>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-800 bg-gray-950 px-1 flex-shrink-0 overflow-x-auto">
        {TABS.map((tab) => {
          const hasData = tabHasData(node, tab.id);
          const isActive = currentTab === tab.id;
          return (
            <button
              key={tab.id}
              className={`px-2 py-1.5 text-[10px] whitespace-nowrap border-b-2 ${
                isActive
                  ? "border-cyan-400 text-cyan-400"
                  : hasData
                    ? "border-transparent text-gray-400 hover:text-gray-200"
                    : "border-transparent text-gray-700 cursor-not-allowed"
              }`}
              onClick={() => hasData && onTabChange(tab.id)}
              disabled={!hasData}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {currentTab === "overview" && (
          <SpanOverviewTab node={node} onSwitchTab={onTabChange} />
        )}
        {currentTab === "input" && <SpanInputTab node={node} />}
        {currentTab === "output" && <SpanOutputTab node={node} />}
        {currentTab === "toolcalls" && <SpanToolCallsTab node={node} />}
        {currentTab === "guardrails" && <SpanGuardrailsTab node={node} />}
        {currentTab === "events" && <SpanEventsTab node={node} />}
        {currentTab === "raw" && <SpanRawTab node={node} />}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Rewrite `ConsoleRightPanel.tsx` with split layout**

```typescript
import { useState, useCallback, useRef, useEffect } from "react";
import { Activity } from "lucide-react";
import { useConsoleStore } from "../../stores/console";
import { buildSpanTree } from "../../utils/trace-tree";
import type { SpanTreeNode } from "../../utils/trace-tree";
import { RunHistoryList } from "./RunHistoryList";
import { TraceTimeline } from "./TraceTimeline";
import { SpanDetailPanel } from "./SpanDetailPanel";

const STORAGE_KEY = "astromesh:detail-panel-height";
const DEFAULT_SPLIT = 0.6;
const MIN_PANEL_PX = 80;

function findSpan(nodes: SpanTreeNode[], id: string): SpanTreeNode | null {
  for (const node of nodes) {
    if (node.span_id === id) return node;
    const found = findSpan(node.children, id);
    if (found) return found;
  }
  return null;
}

export function ConsoleRightPanel() {
  const { runs, activeTraceRunId } = useConsoleStore();
  const activeRun = runs.find((r) => r.id === activeTraceRunId);

  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [splitRatio, setSplitRatio] = useState(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved ? parseFloat(saved) : DEFAULT_SPLIT;
  });

  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  // Persist split ratio
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(splitRatio));
  }, [splitRatio]);

  // Reset selection when active run changes
  useEffect(() => {
    setSelectedSpanId(null);
    setActiveTab("overview");
  }, [activeTraceRunId]);

  const handleMouseDown = useCallback(() => {
    dragging.current = true;
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const y = e.clientY - rect.top;
      const ratio = Math.max(
        MIN_PANEL_PX / rect.height,
        Math.min(1 - MIN_PANEL_PX / rect.height, y / rect.height),
      );
      setSplitRatio(ratio);
    };
    const handleMouseUp = () => {
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  // Resolve selected span
  const tree =
    activeRun?.trace ? buildSpanTree(activeRun.trace.spans) : [];
  const selectedSpan = selectedSpanId
    ? findSpan(tree, selectedSpanId)
    : null;

  return (
    <div className="w-[340px] flex-shrink-0 bg-gray-900 border-l border-gray-800 flex flex-col overflow-hidden">
      <RunHistoryList />

      {activeRun?.trace ? (
        <div ref={containerRef} className="flex-1 flex flex-col min-h-0">
          {/* Timeline section */}
          <div
            className="overflow-y-auto p-3"
            style={{ height: `${splitRatio * 100}%` }}
          >
            <div className="flex justify-between items-center mb-2">
              <div className="flex items-center gap-1 text-[9px] uppercase tracking-[1.5px] text-gray-500 font-semibold">
                <Activity size={12} />
                Trace Timeline
              </div>
            </div>
            <TraceTimeline
              trace={activeRun.trace}
              selectedSpanId={selectedSpanId}
              onSelectSpan={setSelectedSpanId}
              onSelectTab={setActiveTab}
            />
          </div>

          {/* Drag handle */}
          <div
            className="h-1 bg-gray-800 hover:bg-cyan-500/30 cursor-row-resize flex-shrink-0 flex items-center justify-center"
            onMouseDown={handleMouseDown}
          >
            <div className="w-8 h-0.5 bg-gray-600 rounded" />
          </div>

          {/* Detail panel */}
          <div
            className="overflow-hidden border-t border-gray-800"
            style={{ height: `${(1 - splitRatio) * 100}%` }}
          >
            <SpanDetailPanel
              node={selectedSpan}
              activeTab={activeTab}
              onTabChange={setActiveTab}
            />
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-gray-600 text-sm p-3">
          {runs.length === 0
            ? "Run an agent to see traces"
            : "Select a run to view its trace"}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 7: Verify full build**

Run: `cd D:/monaccode/astromesh/astromesh-forge && npm run build`
Expected: Compiles successfully. All components are now wired together.

- [ ] **Step 8: Commit all Task 4 changes**

```bash
cd D:/monaccode/astromesh
git add astromesh-forge/src/components/console/SpanNode.tsx astromesh-forge/src/components/console/TraceTimeline.tsx astromesh-forge/src/components/console/SpanDetailPanel.tsx astromesh-forge/src/components/console/ConsoleRightPanel.tsx astromesh-forge/src/components/console/SpanOverviewTab.tsx astromesh-forge/src/components/console/SpanInputTab.tsx astromesh-forge/src/components/console/SpanOutputTab.tsx astromesh-forge/src/components/console/SpanToolCallsTab.tsx astromesh-forge/src/components/console/SpanGuardrailsTab.tsx astromesh-forge/src/components/console/SpanEventsTab.tsx astromesh-forge/src/components/console/SpanRawTab.tsx
git commit -m "feat(forge): add span detail panel with chips, tabs, and split layout"
```

---

## Task 5: Final verification and lint

**Files:** All modified files

- [ ] **Step 1: Run backend tests**

Run: `cd D:/monaccode/astromesh && uv run pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Lint backend**

Run: `cd D:/monaccode/astromesh && uv run ruff check astromesh/runtime/engine.py tests/test_span_enrichment.py && uv run ruff format astromesh/runtime/engine.py tests/test_span_enrichment.py`

- [ ] **Step 3: Build frontend**

Run: `cd D:/monaccode/astromesh/astromesh-forge && npm run build`
Expected: Compiles with no errors

- [ ] **Step 4: Lint frontend**

Run: `cd D:/monaccode/astromesh/astromesh-forge && npx eslint src/components/console/ src/types/console.ts --fix`

- [ ] **Step 5: Commit any lint fixes**

```bash
cd D:/monaccode/astromesh
git add -A
git diff --cached --stat  # review what's staged
git commit -m "chore: lint fixes for trace timeline detail panel"
```
