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

function formatDuration(ms: number): string {
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

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
        <span className="text-gray-600">{formatDuration(node.duration_ms ?? 0)}</span>
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
      <div className="flex-1 min-h-0 overflow-y-auto">
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
