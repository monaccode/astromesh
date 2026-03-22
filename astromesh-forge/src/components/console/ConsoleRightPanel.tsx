import { useState, useCallback, useRef, useEffect } from "react";
import { Activity, Maximize2, Minimize2, X } from "lucide-react";
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
const MIN_WIDTH = 280;
const MAX_WIDTH = 1200;

function findSpan(nodes: SpanTreeNode[], id: string): SpanTreeNode | null {
  for (const node of nodes) {
    if (node.span_id === id) return node;
    const found = findSpan(node.children, id);
    if (found) return found;
  }
  return null;
}

type DragMode = "none" | "h-resize" | "v-resize";

export function ConsoleRightPanel() {
  const { runs, activeTraceRunId } = useConsoleStore();
  const activeRun = runs.find((r) => r.id === activeTraceRunId);

  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [detailMaximized, setDetailMaximized] = useState(false);

  const [splitRatio, setSplitRatio] = useState(() => {
    const saved = localStorage.getItem(VSPLIT_KEY);
    return saved ? parseFloat(saved) : DEFAULT_VSPLIT;
  });

  const [panelWidth, setPanelWidth] = useState(() => {
    const saved = localStorage.getItem(WIDTH_KEY);
    return saved ? parseInt(saved, 10) : DEFAULT_WIDTH;
  });

  const splitContainerRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const dragMode = useRef<DragMode>("none");

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
    setDetailMaximized(false);
  }, [activeTraceRunId]);

  // Unified drag handler
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (dragMode.current === "v-resize" && splitContainerRef.current) {
        const rect = splitContainerRef.current.getBoundingClientRect();
        const y = e.clientY - rect.top;
        const ratio = Math.max(
          MIN_PANEL_PX / rect.height,
          Math.min(1 - MIN_PANEL_PX / rect.height, y / rect.height),
        );
        setSplitRatio(ratio);
      }

      if (dragMode.current === "h-resize") {
        const newWidth = window.innerWidth - e.clientX;
        setPanelWidth(Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, newWidth)));
      }
    };

    const handleMouseUp = () => {
      dragMode.current = "none";
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

  const startHDrag = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragMode.current = "h-resize";
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  const startVDrag = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragMode.current = "v-resize";
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  }, []);

  // Esc exits maximized
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && detailMaximized) setDetailMaximized(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [detailMaximized]);

  const tree = activeRun?.trace ? buildSpanTree(activeRun.trace.spans) : [];
  const selectedSpan = selectedSpanId ? findSpan(tree, selectedSpanId) : null;

  const handleCloseDetail = useCallback(() => {
    setSelectedSpanId(null);
    setDetailMaximized(false);
  }, []);

  return (
    <div
      ref={panelRef}
      data-right-panel
      className="flex-shrink-0 bg-gray-900 border-l border-gray-800 flex flex-row overflow-hidden"
      style={{ width: panelWidth }}
    >
      {/* Horizontal resize handle — left edge */}
      <div
        className="w-1.5 flex-shrink-0 cursor-col-resize group relative"
        onMouseDown={startHDrag}
        onDoubleClick={() => setPanelWidth(DEFAULT_WIDTH)}
        title="Drag to resize panel width"
      >
        {/* Visible track */}
        <div className="absolute inset-0 bg-gray-800 group-hover:bg-cyan-500/40 active:bg-cyan-500/60 transition-colors" />
        {/* Grip dots */}
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <div className="w-0.5 h-0.5 rounded-full bg-cyan-400" />
          <div className="w-0.5 h-0.5 rounded-full bg-cyan-400" />
          <div className="w-0.5 h-0.5 rounded-full bg-cyan-400" />
        </div>
      </div>

      {/* Panel content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <RunHistoryList />

        {activeRun?.trace ? (
          <div ref={splitContainerRef} className="flex-1 flex flex-col min-h-0">
            {/* Timeline section — hidden when detail is maximized */}
            {!detailMaximized && (
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
            )}

            {/* Detail section */}
            {selectedSpan && (
              <>
                {/* Vertical drag handle — hidden when maximized */}
                {!detailMaximized && (
                  <div
                    className="h-1.5 bg-gray-800 hover:bg-cyan-500/30 cursor-row-resize flex-shrink-0 flex items-center justify-center group transition-colors"
                    onMouseDown={startVDrag}
                  >
                    <div className="w-10 h-0.5 bg-gray-600 group-hover:bg-cyan-400/50 rounded transition-colors" />
                  </div>
                )}

                <div
                  className="overflow-hidden border-t border-gray-800 flex flex-col"
                  style={{
                    height: detailMaximized ? "100%" : `${(1 - splitRatio) * 100}%`,
                  }}
                >
                  {/* Detail toolbar */}
                  <div className="flex items-center justify-end gap-1 px-2 py-0.5 bg-gray-950/50 border-b border-gray-800/50 flex-shrink-0">
                    <button
                      className="text-gray-500 hover:text-cyan-400 transition-colors p-0.5"
                      onClick={() => setDetailMaximized(!detailMaximized)}
                      title={detailMaximized ? "Restore split (Esc)" : "Maximize detail"}
                    >
                      {detailMaximized ? <Minimize2 size={10} /> : <Maximize2 size={10} />}
                    </button>
                    <button
                      className="text-gray-500 hover:text-red-400 transition-colors p-0.5"
                      onClick={handleCloseDetail}
                      title="Close detail"
                    >
                      <X size={10} />
                    </button>
                  </div>

                  {/* Panel content */}
                  <div className="flex-1 min-h-0 overflow-hidden">
                    <SpanDetailPanel
                      node={selectedSpan}
                      activeTab={activeTab}
                      onTabChange={setActiveTab}
                    />
                  </div>
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
