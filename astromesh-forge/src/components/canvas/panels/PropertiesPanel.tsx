import { useNavigate } from "react-router-dom";
import { Button } from "../../ui/Button";
import { Badge } from "../../ui/Badge";
import type { AgentNodeData } from "../../../types/canvas";

interface PropertiesPanelProps {
  nodeData: AgentNodeData | null;
  onClose: () => void;
  onExpandPipeline: () => void;
}

const statusVariant: Record<string, "default" | "success" | "warning" | "danger"> = {
  draft: "default",
  deployed: "success",
  paused: "warning",
};

export function PropertiesPanel({
  nodeData,
  onClose,
  onExpandPipeline,
}: PropertiesPanelProps) {
  const navigate = useNavigate();

  if (!nodeData) return null;

  return (
    <div className="w-[300px] bg-gray-900 border-l border-gray-800 h-full overflow-y-auto shrink-0">
      <div className="p-3 border-b border-gray-800 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Properties
        </h2>
        <button
          className="text-gray-500 hover:text-gray-300 text-lg leading-none"
          onClick={onClose}
        >
          &times;
        </button>
      </div>

      <div className="p-4 space-y-4">
        {/* Agent Summary */}
        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wider">
            Display Name
          </label>
          <div className="text-sm text-gray-200 mt-0.5">
            {nodeData.displayName}
          </div>
        </div>

        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wider">
            Technical Name
          </label>
          <div className="text-sm text-gray-200 mt-0.5">{nodeData.name}</div>
        </div>

        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wider">
            Status
          </label>
          <div className="mt-1">
            <Badge variant={statusVariant[nodeData.status] ?? "default"}>
              {nodeData.status}
            </Badge>
          </div>
        </div>

        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wider">
            Orchestration Pattern
          </label>
          <div className="mt-1">
            <Badge>{nodeData.pattern}</Badge>
          </div>
        </div>

        <hr className="border-gray-800" />

        {/* Actions */}
        <div className="space-y-2">
          <Button
            variant="secondary"
            className="w-full text-sm py-1.5"
            onClick={() => navigate(`/wizard/${nodeData.name}`)}
          >
            Edit in Wizard
          </Button>
          <Button
            variant="primary"
            className="w-full text-sm py-1.5"
            onClick={onExpandPipeline}
          >
            Expand Pipeline
          </Button>
        </div>
      </div>
    </div>
  );
}
