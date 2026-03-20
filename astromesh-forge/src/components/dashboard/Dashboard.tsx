import { useEffect } from "react";
import { useConnectionStore } from "../../stores/connection";
import { AgentList } from "./AgentList";
import { QuickActions } from "./QuickActions";

export function Dashboard() {
  const checkConnection = useConnectionStore((s) => s.checkConnection);

  useEffect(() => {
    checkConnection();
  }, [checkConnection]);

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-100 mb-2">Dashboard</h1>
        <p className="text-gray-400">
          Create, manage, and deploy your AI agents.
        </p>
      </div>

      <section>
        <h2 className="text-lg font-semibold text-gray-200 mb-4">
          Quick Actions
        </h2>
        <QuickActions />
      </section>

      <section>
        <h2 className="text-lg font-semibold text-gray-200 mb-4">
          Your Agents
        </h2>
        <AgentList />
      </section>
    </div>
  );
}
