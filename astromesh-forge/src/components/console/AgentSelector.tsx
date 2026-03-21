import { useEffect, useState } from "react";
import { Bot } from "lucide-react";
import { useConnectionStore } from "../../stores/connection";
import { useConsoleStore } from "../../stores/console";
import type { AgentMeta } from "../../types/agent";
import { Badge } from "../ui/Badge";

export function AgentSelector() {
  const client = useConnectionStore((s) => s.client);
  const connected = useConnectionStore((s) => s.connected);
  const { selectedAgent, selectAgent } = useConsoleStore();
  const [agents, setAgents] = useState<AgentMeta[]>([]);

  useEffect(() => {
    if (!connected) return;
    client.listAgents().then(setAgents).catch(() => setAgents([]));
  }, [client, connected]);

  return (
    <div>
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-[1.5px] text-gray-500 font-semibold mb-1.5">
        <Bot size={12} />
        Agent
      </div>
      <select
        className="w-full bg-gray-800 border border-gray-700 rounded-md px-2.5 py-2 text-sm text-gray-100 focus:outline-none focus:border-cyan-500"
        value={selectedAgent ?? ""}
        onChange={(e) => e.target.value && selectAgent(e.target.value)}
      >
        <option value="">Select an agent...</option>
        {agents.map((a) => (
          <option key={a.name} value={a.name}>
            {a.name}
          </option>
        ))}
      </select>
      {selectedAgent && (
        <div className="mt-1 flex items-center gap-2">
          <Badge variant="success">deployed</Badge>
          <span className="text-gray-500 text-xs">
            {agents.find((a) => a.name === selectedAgent)?.version ?? ""}
          </span>
        </div>
      )}
    </div>
  );
}
