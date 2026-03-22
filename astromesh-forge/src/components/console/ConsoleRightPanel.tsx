import { useState, useCallback, useRef, useEffect } from "react";
import { Activity } from "lucide-react";
import { useConsoleStore } from "../../stores/console";
import { buildSpanTree } from "../../utils/trace-tree";
import type { SpanTreeNode } from "../../utils/trace-tree";
import { RunHistoryList } from "./RunHistoryList";
import { TraceTimeline } from "./TraceTimeline";
import { SpanDetailPanel } from "./SpanDetailPanel";

const VSPLIT_KEY = "astromesh:detail-panel-height";
const WIDTH_KEY = "astromesh:right-panel-width";
const DEFAULT_VSPLIT = 0.5;
const MIN_PANEL_PX = 60;
const DEFAULT_WIDTH = 420;
const MIN_WIDTH = 300;
const MAX_WIDTH = 900;

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

  // Vertical split (timeline / detail)
  const [splitRatio, setSplitRatio] = useState(() => {
    const saved = localStorage.getItem(VSPLIT_KEY);
    return saved ? parseFloat(saved) : DEFAULT_VSPLIT;
  });

  // Horizontal width
  const [panelWidth, setPanelWidth] = useState(() => {
    const saved = localStorage.getItem(WIDTH_KEY);
    return saved ? parseInt(saved, 10) : DEFAULT_WIDTH;
  });

  const containerRef = useRef<HTMLDivElement>(null);
  const vDragging = useRef(false);
  const hDragging = useRef(false);

  // Persist
  useEffect(() => {
    localStorage.setItem(VSPLIT_KEY, String(splitRatio));
  }, [splitRatio]);

  useEffect(() => {
    localStorage.setItem(WIDTH_KEY, String(panelWidth));
  }, [panelWidth]);

  // Reset selection on run change
  useEffect(() => {
    setSelectedSpanId(null);
    setActiveTab("overview");
  }, [activeTraceRunId]);

  // Vertical drag (timeline / detail split)
  const handleVDragStart = useCallback(() => {
    vDragging.current = true;
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  }, []);

  // Horizontal drag (panel width)
  const handleHDragStart = useCallback(() => {
    hDragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    const panelEl = containerRef.current?.closest("[data-right-panel]") as HTMLElement | null;

    const handleMouseMove = (e: MouseEvent) => {
      if (vDragging.current && containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        const y = e.clientY - rect.top;
        const ratio = Math.max(
          MIN_PANEL_PX / rect.height,
          Math.min(1 - MIN_PANEL_PX / rect.height, y / rect.height),
        );
        setSplitRatio(ratio);
      }

      if (hDragging.current && panelEl) {
        // Drag from left edge: width = right edge of viewport - mouseX
        const newWidth = window.innerWidth - e.clientX;
        setPanelWidth(Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, newWidth)));
      }
    };

    const handleMouseUp = () => {
      vDragging.current = false;
      hDragging.current = false;
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

  // Double-click on horizontal handle resets width
  const handleHDoubleClick = useCallback(() => {
    setPanelWidth(DEFAULT_WIDTH);
  }, []);

  const tree = activeRun?.trace ? buildSpanTree(activeRun.trace.spans) : [];
  const selectedSpan = selectedSpanId ? findSpan(tree, selectedSpanId) : null;

  return (
    <div
      data-right-panel
      className="flex-shrink-0 bg-gray-900 border-l border-gray-800 flex flex-row overflow-hidden"
      style={{ width: panelWidth }}
    >
      {/* Horizontal resize handle (left edge) */}
      <div
        className="w-1 flex-shrink-0 cursor-col-resize hover:bg-cyan-500/30 transition-colors group flex items-center justify-center"
        onMouseDown={handleHDragStart}
        onDoubleClick={handleHDoubleClick}
        title="Drag to resize, double-click to reset"
      >
        <div className="w-px h-8 bg-gray-700 group-hover:bg-cyan-400/50 transition-colors" />
      </div>

      {/* Panel content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <RunHistoryList />

        {activeRun?.trace ? (
          <div ref={containerRef} className="flex-1 flex flex-col min-h-0">
            {/* Timeline section */}
            <div
              className="overflow-y-auto p-3"
              style={{
                height: selectedSpan ? `${splitRatio * 100}%` : "100%",
              }}
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

            {/* Vertical split + detail: only when span selected */}
            {selectedSpan && (
              <>
                <div
                  className="h-1.5 bg-gray-800 hover:bg-cyan-500/30 cursor-row-resize flex-shrink-0 flex items-center justify-center group transition-colors"
                  onMouseDown={handleVDragStart}
                >
                  <div className="w-10 h-0.5 bg-gray-600 group-hover:bg-cyan-400/50 rounded transition-colors" />
                </div>

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
              </>
            )}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-600 text-sm p-3">
            {runs.length === 0
              ? "Run an agent to see traces"
              : "Select a run to view its trace"}
          </div>
        )}
      </div>
    </div>
  );
}
