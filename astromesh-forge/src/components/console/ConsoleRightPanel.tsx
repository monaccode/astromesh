import { Activity } from "lucide-react";
import { useConsoleStore } from "../../stores/console";
import { RunHistoryList } from "./RunHistoryList";
import { TraceTimeline } from "./TraceTimeline";

export function ConsoleRightPanel() {
  const { runs, activeTraceRunId } = useConsoleStore();
  const activeRun = runs.find((r) => r.id === activeTraceRunId);

  return (
    <div className="w-[340px] flex-shrink-0 bg-gray-900 border-l border-gray-800 flex flex-col overflow-hidden">
      <RunHistoryList />

      <div className="flex-1 overflow-y-auto p-3">
        {activeRun?.trace ? (
          <>
            <div className="flex justify-between items-center mb-2">
              <div className="flex items-center gap-1 text-[9px] uppercase tracking-[1.5px] text-gray-500 font-semibold">
                <Activity size={12} />
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
