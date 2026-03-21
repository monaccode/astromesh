import { useConsoleStore } from "../../stores/console";
import { RunHistoryList } from "./RunHistoryList";
import { TraceTimeline } from "./TraceTimeline";
import { CompareView } from "./CompareView";

export function ConsoleRightPanel() {
  const { runs, activeTraceRunId, compareSelection } = useConsoleStore();

  const activeRun = runs.find((r) => r.id === activeTraceRunId);
  const isComparing =
    compareSelection !== null && compareSelection[0] !== compareSelection[1];
  const compareRunA = isComparing
    ? runs.find((r) => r.id === compareSelection![0])
    : undefined;
  const compareRunB = isComparing
    ? runs.find((r) => r.id === compareSelection![1])
    : undefined;

  return (
    <div className="w-[340px] flex-shrink-0 bg-gray-900 border-l border-gray-800 flex flex-col overflow-hidden">
      <RunHistoryList />

      <div className="flex-1 overflow-y-auto p-3">
        {isComparing && compareRunA && compareRunB ? (
          <CompareView runA={compareRunA} runB={compareRunB} />
        ) : activeRun?.trace ? (
          <>
            <div className="flex justify-between items-center mb-2">
              <div className="text-[9px] uppercase tracking-[1.5px] text-gray-500 font-semibold">
                Trace Timeline
              </div>
            </div>
            <TraceTimeline trace={activeRun.trace} />
          </>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-600 text-sm">
            {runs.length === 0
              ? "Run an agent to see traces"
              : "Select a run to view its trace"}
          </div>
        )}
      </div>
    </div>
  );
}
