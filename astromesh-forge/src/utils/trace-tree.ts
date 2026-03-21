import type { TraceSpan } from "../types/console";

export interface SpanTreeNode extends TraceSpan {
  children: SpanTreeNode[];
}

export function buildSpanTree(spans: TraceSpan[]): SpanTreeNode[] {
  const map = new Map<string, SpanTreeNode>();
  const roots: SpanTreeNode[] = [];

  for (const span of spans) {
    map.set(span.span_id, { ...span, children: [] });
  }

  for (const node of map.values()) {
    if (node.parent_span_id && map.has(node.parent_span_id)) {
      map.get(node.parent_span_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }

  return roots;
}

const SPAN_COLORS: Record<string, string> = {
  "agent.run": "border-cyan-400",
  memory_build: "border-blue-400",
  memory_persist: "border-blue-400",
  prompt_render: "border-blue-400",
  "llm.complete": "border-amber-400",
};

export function getSpanColor(name: string): string {
  if (SPAN_COLORS[name]) return SPAN_COLORS[name];
  if (name.startsWith("memory")) return "border-blue-400";
  if (name.startsWith("tool.")) return "border-orange-400";
  return "border-gray-500";
}

export function getSpanDotColor(name: string): string {
  if (name === "agent.run") return "text-cyan-400";
  if (name.startsWith("memory") || name === "prompt_render")
    return "text-blue-400";
  if (name === "llm.complete") return "text-amber-400";
  if (name.startsWith("tool.")) return "text-orange-400";
  return "text-gray-400";
}
