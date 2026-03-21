import type { RunRecord } from "../../types/console";
import { TraceTimeline } from "./TraceTimeline";

interface CompareViewProps {
  runA: RunRecord;
  runB: RunRecord;
}

export function CompareView({ runA, runB }: CompareViewProps) {
  if (!runA.trace || !runB.trace) {
    return (
      <div className="text-gray-600 text-xs text-center py-8">
        Both runs must have trace data to compare
      </div>
    );
  }

  return (
    <div className="flex gap-1 flex-1 min-h-0 overflow-auto">
      <div className="flex-1 bg-gray-950 rounded p-2 border-t-2 border-cyan-400 overflow-auto">
        <TraceTimeline
          trace={runA.trace}
          label={`Run — ${(runA.durationMs / 1000).toFixed(1)}s`}
          accentColor="text-cyan-400"
        />
      </div>
      <div className="flex-1 bg-gray-950 rounded p-2 border-t-2 border-orange-400 overflow-auto">
        <TraceTimeline
          trace={runB.trace}
          label={`Run — ${(runB.durationMs / 1000).toFixed(1)}s`}
          accentColor="text-orange-400"
        />
      </div>
    </div>
  );
}
