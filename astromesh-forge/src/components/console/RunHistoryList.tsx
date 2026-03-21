import { History, GitCompareArrows } from "lucide-react";
import { useConsoleStore } from "../../stores/console";

export function RunHistoryList() {
  const { runs, activeTraceRunId, compareSelection, viewTrace, setCompare } =
    useConsoleStore();

  if (runs.length === 0) return null;

  const isComparing = compareSelection !== null;

  const toggleCompare = (runId: string) => {
    if (!compareSelection) {
      setCompare([runId, runId]);
      return;
    }
    const [a, b] = compareSelection;
    if (a === runId && b === runId) {
      setCompare(null);
      return;
    }
    if (a === runId) {
      setCompare(null);
      return;
    }
    setCompare([a, runId]);
  };

  return (
    <div className="border-b border-gray-800 px-3 py-2.5">
      <div className="flex justify-between items-center mb-2">
        <div className="flex items-center gap-1 text-[9px] uppercase tracking-[1.5px] text-gray-500 font-semibold">
          <History size={12} />
          Run History
        </div>
        <button
          className={`flex items-center gap-1 text-[10px] ${isComparing ? "text-red-400" : "text-cyan-400"} hover:underline`}
          onClick={() =>
            setCompare(
              isComparing ? null : [runs[0].id, runs[0].id]
            )
          }
        >
          <GitCompareArrows size={10} />
          {isComparing ? "Exit Compare" : "Compare"}
        </button>
      </div>
      <div className="flex gap-1 overflow-x-auto pb-1">
        {runs.map((run, i) => {
          const isActive = run.id === activeTraceRunId;
          const isSelected =
            compareSelection?.includes(run.id) ?? false;
          const isError = run.trace?.spans.some((s) => s.status === "error");

          return (
            <button
              key={run.id}
              className={`flex-shrink-0 rounded px-2 py-1.5 text-left text-[9px] min-w-[100px] border transition-colors ${
                isActive
                  ? "bg-blue-900/40 border-blue-500"
                  : isSelected
                    ? "bg-cyan-900/20 border-cyan-500"
                    : "bg-gray-800 border-gray-700 hover:border-gray-600"
              }`}
              onClick={() => {
                if (isComparing) {
                  toggleCompare(run.id);
                } else {
                  viewTrace(run.id);
                }
              }}
            >
              <div
                className={`font-medium ${isActive ? "text-gray-100" : "text-gray-400"}`}
              >
                #{i + 1} —{" "}
                {new Date(run.timestamp).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </div>
              <div className="text-gray-500 truncate">
                {run.query.slice(0, 30)}
                {run.query.length > 30 ? "..." : ""} •{" "}
                <span className={isError ? "text-red-400" : ""}>
                  {(run.durationMs / 1000).toFixed(1)}s
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
