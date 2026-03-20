import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { Node } from "@xyflow/react";

type MemoryNodeData = {
  label: string;
  category: string;
  config: Record<string, unknown>;
};

type MemoryNode = Node<MemoryNodeData, "memory">;

export function MemoryNode({ data }: NodeProps<MemoryNode>) {
  const backend = (data.config.backend as string) || "unknown";
  const strategy = (data.config.strategy as string) || "";

  return (
    <div className="bg-gray-800 border-l-4 border-purple-500 rounded-lg p-3 min-w-[200px] shadow-md">
      <Handle type="target" position={Position.Top} className="!bg-gray-500" />
      <div className="text-sm font-medium text-gray-100">{data.label}</div>
      <div className="text-xs text-gray-500 mt-1">
        {backend}{strategy ? ` / ${strategy}` : ""}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-gray-500" />
    </div>
  );
}
