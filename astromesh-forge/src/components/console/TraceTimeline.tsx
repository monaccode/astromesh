import type { Trace } from "../../types/console";
import { buildSpanTree } from "../../utils/trace-tree";
import { SpanNode } from "./SpanNode";

interface TraceTimelineProps {
  trace: Trace;
  label?: string;
  accentColor?: string;
}

export function TraceTimeline({
  trace,
  label,
  accentColor = "text-cyan-400",
}: TraceTimelineProps) {
  const tree = buildSpanTree(trace.spans);
  const rootDuration =
    tree.length > 0 ? (tree[0].duration_ms ?? 0) : 0;

  const totalTokensIn = trace.spans.reduce((acc, s) => {
    const meta = s.attributes.metadata as Record<string, unknown> | undefined;
    const usage = meta?.usage as { prompt_tokens?: number } | undefined;
    return acc + (usage?.prompt_tokens ?? 0);
  }, 0);

  const totalTokensOut = trace.spans.reduce((acc, s) => {
    const meta = s.attributes.metadata as Record<string, unknown> | undefined;
    const usage = meta?.usage as { completion_tokens?: number } | undefined;
    return acc + (usage?.completion_tokens ?? 0);
  }, 0);

  return (
    <div className="flex flex-col gap-1">
      <div className={`text-[10px] ${accentColor} mb-1`}>
        {label && <span className="font-semibold mr-2">{label}</span>}
        trace: {trace.trace_id.slice(0, 8)}
        {rootDuration > 0 && (
          <span className="text-gray-500 ml-2">
            {(rootDuration / 1000).toFixed(1)}s total
          </span>
        )}
        {(totalTokensIn > 0 || totalTokensOut > 0) && (
          <span className="text-gray-500 ml-2">
            {totalTokensIn + totalTokensOut} tokens
          </span>
        )}
      </div>

      {tree.map((node) => (
        <SpanNode key={node.span_id} node={node} rootDuration={rootDuration} />
      ))}

      {tree.length === 0 && (
        <div className="text-gray-600 text-xs text-center py-4">
          No spans in this trace
        </div>
      )}
    </div>
  );
}
