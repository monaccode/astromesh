import type { SpanTreeNode } from "../../utils/trace-tree";

export function SpanInputTab({ node }: { node: SpanTreeNode }) {
  const prompt = node.attributes.prompt;
  if (!prompt) {
    return (
      <div className="text-gray-600 text-xs text-center py-8">
        No prompt data available for this span
      </div>
    );
  }

  return (
    <div className="p-3">
      <pre className="text-gray-300 bg-gray-800 rounded p-3 text-[10px] whitespace-pre-wrap break-words overflow-y-auto max-h-[400px]">
        {prompt as string}
      </pre>
    </div>
  );
}
