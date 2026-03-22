import type { SpanTreeNode } from "../../utils/trace-tree";

export function SpanEventsTab({ node }: { node: SpanTreeNode }) {
  if (node.events.length === 0) {
    return (
      <div className="text-gray-600 text-xs text-center py-8">
        No events for this span
      </div>
    );
  }

  const spanStart = node.start_time;

  return (
    <div className="p-3 flex flex-col gap-1.5 text-[11px]">
      {node.events.map((event, i) => {
        const relativeMs = Math.round((event.timestamp - spanStart) * 1000);
        return (
          <div key={i} className="bg-gray-800 rounded p-2">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-gray-500 font-mono text-[9px] w-14 text-right flex-shrink-0">
                +{relativeMs}ms
              </span>
              <span className="text-cyan-400 font-semibold">{event.name}</span>
            </div>
            {Object.keys(event.attributes).length > 0 && (
              <pre className="text-gray-400 bg-gray-900 rounded p-2 text-[9px] overflow-x-auto ml-16">
                {JSON.stringify(event.attributes, null, 2)}
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}
