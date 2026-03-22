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
