import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { Node } from "@xyflow/react";

type ModelNodeData = {
  label: string;
  category: string;
  config: Record<string, unknown>;
};

type ModelNode = Node<ModelNodeData, "model">;

export function ModelNode({ data }: NodeProps<ModelNode>) {
  const params = data.config.parameters as Record<string, unknown> | undefined;
  const paramSummary = params
    ? Object.entries(params)
        .map(([k, v]) => `${k}: ${v}`)
        .join(", ")
    : null;

  return (
    <div className="bg-gray-800 border-l-4 border-blue-500 rounded-lg p-3 min-w-[200px] shadow-md">
      <Handle type="target" position={Position.Top} className="!bg-gray-500" />
      <div className="text-sm font-medium text-gray-100">{data.label}</div>
      {paramSummary && (
        <div className="text-xs text-gray-500 mt-1 truncate">{paramSummary}</div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-gray-500" />
    </div>
  );
}
