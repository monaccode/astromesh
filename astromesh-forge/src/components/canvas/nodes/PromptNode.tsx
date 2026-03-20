import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { Node } from "@xyflow/react";

type PromptNodeData = {
  label: string;
  category: string;
  config: Record<string, unknown>;
};

type PromptNode = Node<PromptNodeData, "prompt">;

export function PromptNode({ data }: NodeProps<PromptNode>) {
  const system = (data.config.system as string) || "";
  const preview = system.length > 80 ? system.slice(0, 80) + "..." : system;

  return (
    <div className="bg-gray-800 border-l-4 border-yellow-500 rounded-lg p-3 min-w-[200px] shadow-md">
      <Handle type="target" position={Position.Top} className="!bg-gray-500" />
      <div className="text-sm font-medium text-gray-100">{data.label}</div>
      {preview && (
        <div className="text-xs text-gray-500 mt-1 italic">{preview}</div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-gray-500" />
    </div>
  );
}
