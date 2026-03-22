import type { SpanTreeNode } from "../../utils/trace-tree";

export function SpanGuardrailsTab({ node }: { node: SpanTreeNode }) {
  const guardrailEvents = node.events.filter((e) => e.name === "guardrail");

  if (guardrailEvents.length === 0) {
    return (
      <div className="text-gray-600 text-xs text-center py-8">
        No guardrail events for this span
      </div>
    );
  }

  return (
    <div className="p-3 flex flex-col gap-2 text-[11px]">
      {guardrailEvents.map((event, i) => {
        const ea = event.attributes;
        const action = ea.action as string;
        const actionColor =
          action === "block"
            ? "text-red-400"
            : action === "redact"
              ? "text-amber-400"
              : "text-green-400";

        return (
          <div key={i} className="bg-gray-800 rounded p-2">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-purple-400 font-semibold">
                {String(ea.guardrail_name)}
              </span>
              <span className="text-gray-500 text-[9px] uppercase">
                {String(ea.guardrail_type)}
              </span>
              <span className={`${actionColor} text-[9px] font-semibold uppercase`}>
                {action}
              </span>
            </div>
            {ea.details != null && (
              <pre className="text-gray-400 bg-gray-900 rounded p-2 text-[9px] overflow-x-auto">
                {JSON.stringify(ea.details, null, 2)}
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}
