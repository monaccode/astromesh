import { ArrowUp, ArrowDown } from "lucide-react";
import { useConsoleStore } from "../../stores/console";

export function RunSummaryBar() {
  const { runs } = useConsoleStore();

  if (runs.length === 0) return null;

  const totalIn = runs.reduce((sum, r) => sum + (r.usage?.tokens_in ?? 0), 0);
  const totalOut = runs.reduce((sum, r) => sum + (r.usage?.tokens_out ?? 0), 0);
  const totalDuration = runs.reduce((sum, r) => sum + r.durationMs, 0);
  const lastModel = runs.findLast((r) => r.usage?.model)?.usage?.model ?? "—";

  return (
    <div className="px-4 py-1.5 border-t border-gray-800 bg-gray-950 flex items-center gap-4 text-[10px]">
      <div className="flex items-center gap-1 text-gray-400">
        <span className="inline-flex items-center gap-0.5 text-cyan-400">
          <ArrowUp size={10} /> {totalIn}
        </span>
        {" / "}
        <span className="inline-flex items-center gap-0.5 text-amber-400">
          <ArrowDown size={10} /> {totalOut}
        </span>
        {" tokens"}
      </div>
      <div className="text-gray-500">{lastModel}</div>
      <div className="text-gray-500">
        {(totalDuration / 1000).toFixed(1)}s total
      </div>
      <div className="flex-1" />
      <div className="text-gray-500">
        {runs.length} {runs.length === 1 ? "run" : "runs"}
      </div>
    </div>
  );
}
