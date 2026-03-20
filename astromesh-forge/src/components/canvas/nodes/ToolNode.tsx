import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { Node } from "@xyflow/react";
import { Badge } from "../../ui/Badge";

type ToolNodeData = {
  label: string;
  category: string;
  config: Record<string, unknown>;
};

type ToolNode = Node<ToolNodeData, "tool">;

export function ToolNode({ data }: NodeProps<ToolNode>) {
  const toolType = (data.config.type as string) || "internal";

  return (
    <div className="bg-gray-800 border-l-4 border-green-500 rounded-lg p-3 min-w-[200px] shadow-md">
      <Handle type="target" position={Position.Top} className="!bg-gray-500" />
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-gray-100">{data.label}</div>
        <Badge variant="success">{String(toolType)}</Badge>
      </div>
      {data.config.description ? (
        <div className="text-xs text-gray-500 mt-1 truncate">
          {String(data.config.description)}
        </div>
      ) : null}
      <Handle type="source" position={Position.Bottom} className="!bg-gray-500" />
    </div>
  );
}
