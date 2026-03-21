import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, Rocket } from "lucide-react";
import type { AgentConfig } from "../../types/agent";
import { ForgeClient } from "../../api/client";
import { useConnectionStore } from "../../stores/connection";
import { agentToYaml } from "../../utils/yaml";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";
import { TargetSelector, type DeployTarget } from "./TargetSelector";

interface DeployModalProps {
  open: boolean;
  onClose: () => void;
  config: AgentConfig;
}

export function DeployModal({ open, onClose, config }: DeployModalProps) {
  const navigate = useNavigate();
  const localClient = useConnectionStore((s) => s.client);
  const nodeUrl = useConnectionStore((s) => s.nodeUrl);

  const [target, setTarget] = useState<DeployTarget>({ type: "local", url: nodeUrl });
  const [yamlExpanded, setYamlExpanded] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [status, setStatus] = useState<{ type: "success" | "error"; message: string } | null>(
    null
  );

  function getClient(): ForgeClient {
    if (target.type === "local") return localClient;
    return new ForgeClient(target.url);
  }

  async function handleDeploy() {
    setDeploying(true);
    setStatus(null);

    const client = getClient();
    const name = config.metadata.name;

    try {
      // Create or update
      try {
        await client.createAgent(config);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        if (message.includes("409")) {
          await client.updateAgent(name, config);
        } else {
          throw err;
        }
      }

      // Deploy
      await client.deployAgent(name);
      setStatus({ type: "success", message: `Agent "${name}" deployed successfully.` });

      // Close and navigate after short delay
      setTimeout(() => {
        onClose();
        navigate("/");
      }, 1500);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setStatus({ type: "error", message: `Deploy failed: ${message}` });
    } finally {
      setDeploying(false);
    }
  }

  const yamlContent = agentToYaml(config);

  return (
    <Modal open={open} onClose={onClose} title="Deploy Agent">
      <div className="flex flex-col gap-5">
        {/* YAML Preview (collapsible) */}
        <div>
          <button
            className="text-sm text-gray-400 hover:text-gray-200 transition-colors flex items-center gap-1"
            onClick={() => setYamlExpanded(!yamlExpanded)}
          >
            <ChevronRight
              size={14}
              className={`transition-transform ${yamlExpanded ? "rotate-90" : ""}`}
            />
            YAML Preview
          </button>
          {yamlExpanded && (
            <pre className="mt-2 bg-gray-950 border border-gray-700 rounded-lg p-3 text-xs text-gray-300 font-mono overflow-x-auto max-h-48 overflow-y-auto">
              {yamlContent}
            </pre>
          )}
        </div>

        {/* Target Selector */}
        <TargetSelector value={target} onChange={setTarget} />

        {/* Status Feedback */}
        {status && (
          <div
            className={`text-sm rounded-lg p-3 ${
              status.type === "success"
                ? "bg-green-500/10 text-green-400 border border-green-500/20"
                : "bg-red-500/10 text-red-400 border border-red-500/20"
            }`}
          >
            {status.message}
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <Button variant="ghost" onClick={onClose} disabled={deploying}>
            Cancel
          </Button>
          <Button icon={Rocket} onClick={handleDeploy} disabled={deploying}>
            {deploying ? "Deploying..." : "Deploy"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
