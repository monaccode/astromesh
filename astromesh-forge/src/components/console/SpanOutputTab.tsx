import type { SpanTreeNode } from "../../utils/trace-tree";

export function SpanOutputTab({ node }: { node: SpanTreeNode }) {
  const response = node.attributes.response;
  const toolResult = node.attributes.tool_result;
  const content = response ?? toolResult;

  if (!content) {
    return (
      <div className="text-gray-600 text-xs text-center py-8">
        No output data available for this span
      </div>
    );
  }

  return (
    <div className="p-3 h-full">
      <pre className="text-gray-300 bg-gray-800 rounded p-3 text-[10px] whitespace-pre-wrap break-words overflow-y-auto h-full">
        {content as string}
      </pre>
    </div>
  );
}
