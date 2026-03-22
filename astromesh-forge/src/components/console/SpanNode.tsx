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

function formatDuration(ms: number): string {
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

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
        } cursor-pointer mb-0.5 ${isSelected ? "ring-1 ring-cyan-500/50 bg-gray-800/80" : ""}`}
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
            {formatDuration(duration)}
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
