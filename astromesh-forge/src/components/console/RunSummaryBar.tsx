import { useConsoleStore } from "../../stores/console";

export function RunSummaryBar() {
  const { runs, activeTraceRunId } = useConsoleStore();
  const activeRun = runs.find((r) => r.id === activeTraceRunId);

  if (!activeRun) return null;

  const runIndex = runs.findIndex((r) => r.id === activeTraceRunId) + 1;

  return (
    <div className="px-4 py-1.5 border-t border-gray-800 bg-gray-950 flex items-center gap-4 text-[10px]">
      <div className="flex items-center gap-1 text-gray-400">
        <span className="text-cyan-400">&#x2B06; {activeRun.usage?.tokens_in ?? 0}</span>
        {" / "}
        <span className="text-amber-400">&#x2B07; {activeRun.usage?.tokens_out ?? 0}</span>
        {" tokens"}
      </div>
      <div className="text-gray-500">{activeRun.usage?.model ?? "—"}</div>
      <div className="text-gray-500">
        {(activeRun.durationMs / 1000).toFixed(1)}s
      </div>
      <div className="flex-1" />
      <div className="text-gray-500">
        Run #{runIndex} of {runs.length}
      </div>
    </div>
  );
}
