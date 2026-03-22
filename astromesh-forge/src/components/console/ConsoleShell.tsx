import { useState, useCallback, useRef, useEffect } from "react";
import { Minimize2, X } from "lucide-react";
import { useConsoleStore } from "../../stores/console";
import { ConsoleLeftPanel } from "./ConsoleLeftPanel";
import { ConsoleCenterPanel } from "./ConsoleCenterPanel";
import { ConsoleRightPanel } from "./ConsoleRightPanel";
import type { PopoutDetail } from "./ConsoleRightPanel";
import { CompareView } from "./CompareView";
import { SpanDetailPanel } from "./SpanDetailPanel";

const POPOUT_WIDTH_KEY = "astromesh:popout-panel-width";
const DEFAULT_POPOUT_WIDTH = 520;
const MIN_POPOUT = 320;
const MAX_POPOUT = 1000;

export function ConsoleShell() {
  const { runs, compareSelection } = useConsoleStore();

  const isComparing =
    compareSelection !== null && compareSelection[0] !== compareSelection[1];
  const compareRunA = isComparing
    ? runs.find((r) => r.id === compareSelection![0])
    : undefined;
  const compareRunB = isComparing
    ? runs.find((r) => r.id === compareSelection![1])
    : undefined;

  // Popout detail state
  const [popoutDetail, setPopoutDetail] = useState<PopoutDetail | null>(null);
  const [popoutTab, setPopoutTab] = useState("overview");
  const [popoutWidth, setPopoutWidth] = useState(() => {
    const saved = localStorage.getItem(POPOUT_WIDTH_KEY);
    return saved ? parseInt(saved, 10) : DEFAULT_POPOUT_WIDTH;
  });

  const dragging = useRef(false);

  useEffect(() => {
    localStorage.setItem(POPOUT_WIDTH_KEY, String(popoutWidth));
  }, [popoutWidth]);

  // Sync tab from popout trigger
  useEffect(() => {
    if (popoutDetail) setPopoutTab(popoutDetail.tab);
  }, [popoutDetail]);

  // Drag for popout width
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      // The popout panel is the rightmost element; its left edge = e.clientX
      // popoutWidth = viewport right - mouse position - right panel width
      // But simpler: we know the popout is between the right panel and its own left edge
      // Get the right panel element to find where the popout should start
      const rightPanel = document.querySelector("[data-right-panel]");
      if (!rightPanel) return;
      const rightRect = rightPanel.getBoundingClientRect();
      const newWidth = rightRect.left - e.clientX;
      setPopoutWidth(Math.max(MIN_POPOUT, Math.min(MAX_POPOUT, newWidth)));
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

  const startPopoutDrag = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  // Esc closes popout
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && popoutDetail) setPopoutDetail(null);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [popoutDetail]);

  const handlePopoutDetail = useCallback((detail: PopoutDetail | null) => {
    setPopoutDetail(detail);
  }, []);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] min-w-[1280px]">
      <ConsoleLeftPanel />
      {isComparing && compareRunA && compareRunB ? (
        <CompareView runA={compareRunA} runB={compareRunB} />
      ) : (
        <>
          <ConsoleCenterPanel />

          {/* Popout detail panel — between center and right */}
          {popoutDetail && (
            <div
              className="flex-shrink-0 bg-gray-950 border-l border-gray-800 flex flex-row overflow-hidden"
              style={{ width: popoutWidth }}
            >
              {/* Resize handle */}
              <div
                className="w-1.5 flex-shrink-0 cursor-col-resize group relative"
                onMouseDown={startPopoutDrag}
                onDoubleClick={() => setPopoutWidth(DEFAULT_POPOUT_WIDTH)}
                title="Drag to resize"
              >
                <div className="absolute inset-0 bg-gray-800 group-hover:bg-cyan-500/40 transition-colors" />
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <div className="w-0.5 h-0.5 rounded-full bg-cyan-400" />
                  <div className="w-0.5 h-0.5 rounded-full bg-cyan-400" />
                  <div className="w-0.5 h-0.5 rounded-full bg-cyan-400" />
                </div>
              </div>

              {/* Content */}
              <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                {/* Toolbar */}
                <div className="flex items-center justify-between px-3 py-1.5 bg-gray-900 border-b border-gray-800 flex-shrink-0">
                  <span className="text-[9px] uppercase tracking-[1.5px] text-gray-500 font-semibold">
                    Span Detail
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      className="text-gray-500 hover:text-cyan-400 transition-colors p-0.5"
                      onClick={() => setPopoutDetail(null)}
                      title="Close panel (Esc)"
                    >
                      <Minimize2 size={11} />
                    </button>
                    <button
                      className="text-gray-500 hover:text-red-400 transition-colors p-0.5"
                      onClick={() => setPopoutDetail(null)}
                      title="Close"
                    >
                      <X size={11} />
                    </button>
                  </div>
                </div>

                {/* Full-height detail */}
                <div className="flex-1 min-h-0 overflow-hidden">
                  <SpanDetailPanel
                    node={popoutDetail.span}
                    activeTab={popoutTab}
                    onTabChange={setPopoutTab}
                  />
                </div>
              </div>
            </div>
          )}

          <ConsoleRightPanel
            onPopoutDetail={handlePopoutDetail}
            popoutDetail={popoutDetail}
          />
        </>
      )}
    </div>
  );
}
