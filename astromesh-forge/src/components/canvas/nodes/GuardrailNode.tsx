import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { Node } from "@xyflow/react";
import { Badge } from "../../ui/Badge";

type GuardrailNodeData = {
  label: string;
  category: string;
  config: Record<string, unknown>;
};

type GuardrailNode = Node<GuardrailNodeData, "guardrail">;

export function GuardrailNode({ data }: NodeProps<GuardrailNode>) {
  const isInput = data.label.startsWith("Input:");
  const borderColor = isInput ? "border-orange-500" : "border-red-500";
  const action = (data.config.action as string) || "block";

  return (
    <div className={`bg-gray-800 border-l-4 ${borderColor} rounded-lg p-3 min-w-[200px] shadow-md`}>
      <Handle type="target" position={Position.Top} className="!bg-gray-500" />
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-gray-100">{data.label}</div>
        <Badge variant={isInput ? "warning" : "danger"}>{action}</Badge>
      </div>
      <div className="text-xs text-gray-500 mt-1">
        {data.config.type as string}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-gray-500" />
    </div>
  );
}
