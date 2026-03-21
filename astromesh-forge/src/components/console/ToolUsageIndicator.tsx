interface ToolUsageIndicatorProps {
  steps: Array<Record<string, unknown>>;
}

export function ToolUsageIndicator({ steps }: ToolUsageIndicatorProps) {
  const toolCalls = steps.filter(
    (s) => s.type === "tool_call" || s.tool || s.name,
  );

  if (toolCalls.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1 mb-2">
      {toolCalls.map((step, i) => {
        const name =
          (step.tool as string) || (step.name as string) || `tool_${i}`;
        const duration = step.duration_ms as number | undefined;
        const hasError = step.status === "error" || step.error;

        return (
          <span
            key={i}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[9px] font-medium ${
              hasError
                ? "bg-red-500/20 text-red-400"
                : "bg-green-500/20 text-green-400"
            }`}
          >
            <span className="text-[8px]">{hasError ? "✕" : "⚡"}</span>
            {name}
            {duration != null && (
              <span className="opacity-70">{duration}ms</span>
            )}
          </span>
        );
      })}
    </div>
  );
}
