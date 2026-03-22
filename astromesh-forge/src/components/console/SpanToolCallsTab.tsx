import type { SpanTreeNode } from "../../utils/trace-tree";

export function SpanToolCallsTab({ node }: { node: SpanTreeNode }) {
  const a = node.attributes;
  const toolCalls = a.tool_calls as
    | Array<{ id?: string; name: string; arguments: Record<string, unknown> }>
    | undefined;
  const isToolSpan = node.name.startsWith("tool.");

  if (!toolCalls?.length && !isToolSpan) {
    return (
      <div className="text-gray-600 text-xs text-center py-8">
        No tool call data available for this span
      </div>
    );
  }

  return (
    <div className="p-3 flex flex-col gap-3 text-[11px]">
      {/* LLM tool_calls */}
      {toolCalls?.map((tc, i) => (
        <div key={i} className="bg-gray-800 rounded p-2">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-orange-400 font-semibold">{tc.name}</span>
            {tc.id && <span className="text-gray-600 text-[9px]">{tc.id}</span>}
          </div>
          <pre className="text-green-400 bg-gray-900 rounded p-2 text-[9px] overflow-x-auto">
            {JSON.stringify(tc.arguments, null, 2)}
          </pre>
        </div>
      ))}

      {/* Tool span details */}
      {isToolSpan && (
        <div className="bg-gray-800 rounded p-2">
          <div className="text-orange-400 font-semibold mb-1">{a.tool as string}</div>
          {a.tool_args && (
            <div className="mb-2">
              <div className="text-gray-500 text-[9px] uppercase mb-0.5">Arguments</div>
              <pre className="text-green-400 bg-gray-900 rounded p-2 text-[9px] overflow-x-auto">
                {JSON.stringify(a.tool_args, null, 2)}
              </pre>
            </div>
          )}
          {a.tool_result && (
            <div>
              <div className="text-gray-500 text-[9px] uppercase mb-0.5">Result</div>
              <pre className="text-gray-300 bg-gray-900 rounded p-2 text-[9px] overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto">
                {a.tool_result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
