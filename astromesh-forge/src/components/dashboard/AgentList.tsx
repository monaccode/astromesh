import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAgentsListStore } from "../../stores/agents-list";
import { useConnectionStore } from "../../stores/connection";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Modal } from "../ui/Modal";

const statusVariant = {
  draft: "default" as const,
  deployed: "success" as const,
  paused: "warning" as const,
};

export function AgentList() {
  const { agents, loading, error, setAgents, setLoading, setError } =
    useAgentsListStore();
  const client = useConnectionStore((s) => s.client);
  const connected = useConnectionStore((s) => s.connected);

  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  useEffect(() => {
    if (!connected) return;
    fetchAgents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected]);

  async function fetchAgents() {
    setLoading(true);
    try {
      const list = await client.listAgents();
      setAgents(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch agents");
    } finally {
      setLoading(false);
    }
  }

  async function handleDeploy(name: string) {
    try {
      await client.deployAgent(name);
      await fetchAgents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deploy failed");
    }
  }

  async function handlePause(name: string) {
    try {
      await client.pauseAgent(name);
      await fetchAgents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pause failed");
    }
  }

  async function handleDelete(name: string) {
    try {
      await client.deleteAgent(name);
      setDeleteTarget(null);
      await fetchAgents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  if (loading) {
    return <p className="text-gray-400">Loading agents...</p>;
  }

  if (error) {
    return (
      <div className="text-red-400">
        <p>Error: {error}</p>
        <Button variant="secondary" className="mt-2" onClick={fetchAgents}>
          Retry
        </Button>
      </div>
    );
  }

  if (!connected) {
    return (
      <p className="text-gray-500">
        Connect to an Astromesh node to view agents.
      </p>
    );
  }

  if (agents.length === 0) {
    return <p className="text-gray-500">No agents yet. Create one above!</p>;
  }

  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-gray-700 text-gray-400 text-sm">
              <th className="pb-3 pr-4">Name</th>
              <th className="pb-3 pr-4">Status</th>
              <th className="pb-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((agent) => (
              <tr
                key={agent.name}
                className="border-b border-gray-700/50 hover:bg-gray-800/50"
              >
                <td className="py-3 pr-4">
                  <div>
                    <span className="text-gray-100 font-medium">
                      {agent.description || agent.name}
                    </span>
                    <span className="block text-xs text-gray-500">
                      {agent.name}
                    </span>
                  </div>
                </td>
                <td className="py-3 pr-4">
                  <Badge variant={statusVariant[agent.status]}>
                    {agent.status}
                  </Badge>
                </td>
                <td className="py-3">
                  <div className="flex gap-2">
                    <Link to={`/wizard/${agent.name}`}>
                      <Button variant="ghost" className="text-sm px-2 py-1">
                        Edit
                      </Button>
                    </Link>
                    {agent.status !== "deployed" && (
                      <Button
                        variant="ghost"
                        className="text-sm px-2 py-1 text-green-400"
                        onClick={() => handleDeploy(agent.name)}
                      >
                        Deploy
                      </Button>
                    )}
                    {agent.status === "deployed" && (
                      <Button
                        variant="ghost"
                        className="text-sm px-2 py-1 text-yellow-400"
                        onClick={() => handlePause(agent.name)}
                      >
                        Pause
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      className="text-sm px-2 py-1 text-red-400"
                      onClick={() => setDeleteTarget(agent.name)}
                    >
                      Delete
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title="Delete Agent"
      >
        <p className="text-gray-300 mb-4">
          Are you sure you want to delete{" "}
          <span className="font-semibold text-gray-100">{deleteTarget}</span>?
          This action cannot be undone.
        </p>
        <div className="flex gap-3 justify-end">
          <Button variant="secondary" onClick={() => setDeleteTarget(null)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={() => deleteTarget && handleDelete(deleteTarget)}
          >
            Delete
          </Button>
        </div>
      </Modal>
    </>
  );
}
