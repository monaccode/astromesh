import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAgentEditorStore } from "../../stores/agent";
import { useConnectionStore } from "../../stores/connection";
import { agentToYaml } from "../../utils/yaml";
import { Button } from "../ui/Button";
import { Modal } from "../ui/Modal";

export function StepReview() {
  const config = useAgentEditorStore((s) => s.config);
  const client = useConnectionStore((s) => s.client);
  const navigate = useNavigate();

  const [showDeploy, setShowDeploy] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const yamlPreview = agentToYaml(config);

  async function handleDeploy() {
    setDeploying(true);
    setError(null);
    try {
      await client.createAgent(config);
      await client.deployAgent(config.metadata.name);
      setShowDeploy(false);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deployment failed");
    } finally {
      setDeploying(false);
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-gray-100">Review & Deploy</h2>

      <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
          <span className="text-sm text-gray-400">agent.yaml</span>
        </div>
        <pre className="p-4 text-sm text-gray-300 overflow-x-auto font-mono leading-relaxed max-h-[500px] overflow-y-auto">
          {yamlPreview}
        </pre>
      </div>

      <div className="flex gap-3">
        <Button onClick={() => setShowDeploy(true)}>Deploy Agent</Button>
        <Button variant="secondary" onClick={() => navigate("/canvas")}>
          Open in Canvas
        </Button>
      </div>

      <Modal
        open={showDeploy}
        onClose={() => setShowDeploy(false)}
        title="Deploy Agent"
      >
        <p className="text-gray-300 mb-2">
          This will create and deploy{" "}
          <span className="font-semibold text-gray-100">
            {config.metadata.name || "unnamed-agent"}
          </span>
          .
        </p>
        {error && <p className="text-red-400 text-sm mb-3">{error}</p>}
        <div className="flex gap-3 justify-end mt-4">
          <Button variant="secondary" onClick={() => setShowDeploy(false)}>
            Cancel
          </Button>
          <Button onClick={handleDeploy} disabled={deploying}>
            {deploying ? "Deploying..." : "Confirm Deploy"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
