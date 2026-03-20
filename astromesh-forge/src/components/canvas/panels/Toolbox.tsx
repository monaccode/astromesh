import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useConnectionStore } from "../../../stores/connection";
import type { AgentMeta } from "../../../types/agent";
import { Button } from "../../ui/Button";
import { Badge } from "../../ui/Badge";

interface ToolboxProps {
  onAddAgent: (agent: AgentMeta) => void;
}

export function Toolbox({ onAddAgent }: ToolboxProps) {
  const navigate = useNavigate();
  const client = useConnectionStore((s) => s.client);
  const connected = useConnectionStore((s) => s.connected);

  const [agents, setAgents] = useState<AgentMeta[]>([]);
  const [agentsExpanded, setAgentsExpanded] = useState(true);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!connected) return;
    setLoading(true);
    client
      .listAgents()
      .then(setAgents)
      .catch(() => setAgents([]))
      .finally(() => setLoading(false));
  }, [client, connected]);

  return (
    <div className="w-[250px] bg-gray-900 border-r border-gray-800 h-full overflow-y-auto shrink-0">
      <div className="p-3 border-b border-gray-800">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Toolbox
        </h2>
      </div>

      {/* Agents Section */}
      <div className="border-b border-gray-800">
        <button
          className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-gray-300 hover:bg-gray-800 transition-colors"
          onClick={() => setAgentsExpanded(!agentsExpanded)}
        >
          <span>Agents</span>
          <span className="text-gray-500 text-xs">
            {agentsExpanded ? "\u25B2" : "\u25BC"}
          </span>
        </button>

        {agentsExpanded && (
          <div className="px-2 pb-2 space-y-1">
            {loading && (
              <div className="text-xs text-gray-500 px-2 py-1">Loading...</div>
            )}
            {!loading && !connected && (
              <div className="text-xs text-gray-500 px-2 py-1">
                Not connected
              </div>
            )}
            {!loading &&
              agents.map((agent) => (
                <button
                  key={agent.name}
                  className="w-full text-left bg-gray-800 hover:bg-gray-750 border border-gray-700 hover:border-gray-600 rounded-lg p-2 transition-colors"
                  onClick={() => onAddAgent(agent)}
                >
                  <div className="text-sm font-medium text-gray-200 truncate">
                    {agent.name}
                  </div>
                  <div className="text-xs text-gray-500 truncate">
                    {agent.description || "No description"}
                  </div>
                  <div className="mt-1">
                    <Badge
                      variant={
                        agent.status === "deployed"
                          ? "success"
                          : agent.status === "paused"
                            ? "warning"
                            : "default"
                      }
                    >
                      {agent.status}
                    </Badge>
                  </div>
                </button>
              ))}

            <Button
              variant="secondary"
              className="w-full mt-1 text-sm py-1.5"
              onClick={() => navigate("/wizard")}
            >
              + Create New Agent
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
