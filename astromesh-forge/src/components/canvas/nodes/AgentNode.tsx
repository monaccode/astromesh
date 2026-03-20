import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { Node } from "@xyflow/react";
import { Badge } from "../../ui/Badge";

type AgentNodeData = {
  name: string;
  displayName: string;
  status: "draft" | "deployed" | "paused";
  pattern: string;
};

type AgentNode = Node<AgentNodeData, "agent">;

const statusVariant: Record<string, "default" | "success" | "warning" | "danger"> = {
  draft: "default",
  deployed: "success",
  paused: "warning",
};

const avatarColors = [
  "bg-cyan-500",
  "bg-violet-500",
  "bg-emerald-500",
  "bg-rose-500",
  "bg-amber-500",
  "bg-sky-500",
];

function getAvatarColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return avatarColors[Math.abs(hash) % avatarColors.length];
}

export function AgentNode({ data }: NodeProps<AgentNode>) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 min-w-[220px] shadow-lg cursor-pointer hover:border-gray-500 transition-colors">
      <Handle type="target" position={Position.Top} className="!bg-gray-500" />
      <div className="flex items-center gap-3">
        <div
          className={`${getAvatarColor(data.displayName)} w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-lg shrink-0`}
        >
          {data.displayName.charAt(0).toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className="text-sm font-semibold text-gray-100 truncate">
            {data.displayName}
          </div>
          <div className="text-xs text-gray-500 truncate">{data.name}</div>
        </div>
      </div>
      <div className="flex items-center gap-2 mt-3">
        <Badge variant={statusVariant[data.status] ?? "default"}>
          {data.status}
        </Badge>
        <Badge>{data.pattern}</Badge>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-gray-500" />
    </div>
  );
}
