import type { SpanTreeNode } from "../../utils/trace-tree";

export function SpanInputTab({ node }: { node: SpanTreeNode }) {
  const a = node.attributes;
  const sections: Array<{ label: string; content: string; color: string }> = [];

  if (a.query)
    sections.push({ label: "User Query", content: a.query as string, color: "text-purple-400" });
  if (a.input_messages)
    sections.push({ label: "Input Messages", content: a.input_messages as string, color: "text-purple-400" });
  if (a.prompt)
    sections.push({ label: "System Prompt", content: a.prompt as string, color: "text-cyan-400" });

  if (sections.length === 0) {
    return (
      <div className="text-gray-600 text-xs text-center py-8">
        No input data available for this span
      </div>
    );
  }

  return (
    <div className="p-3 flex flex-col gap-3 h-full overflow-y-auto">
      {sections.map((s, i) => (
        <div key={i}>
          <div className={`text-[9px] uppercase tracking-wider mb-1 font-semibold ${s.color}`}>
            {s.label}
          </div>
          <pre className="text-gray-300 bg-gray-800 rounded p-3 text-[10px] whitespace-pre-wrap break-words overflow-y-auto max-h-[300px]">
            {s.content}
          </pre>
        </div>
      ))}
    </div>
  );
}
