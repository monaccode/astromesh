import { useState } from "react";
import { ForgeClient } from "../../api/client";
import { useConnectionStore } from "../../stores/connection";
import { Card } from "../ui/Card";
import { Input } from "../ui/Input";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";

export interface DeployTarget {
  type: "local" | "remote";
  url: string;
  apiKey?: string;
}

interface TargetSelectorProps {
  value: DeployTarget;
  onChange: (target: DeployTarget) => void;
}

export function TargetSelector({ value, onChange }: TargetSelectorProps) {
  const { nodeUrl, connected } = useConnectionStore();

  const [remoteUrl, setRemoteUrl] = useState("");
  const [remoteApiKey, setRemoteApiKey] = useState("");
  const [testingConnection, setTestingConnection] = useState(false);
  const [remoteConnected, setRemoteConnected] = useState<boolean | null>(null);

  function selectLocal() {
    onChange({ type: "local", url: nodeUrl });
  }

  function selectRemote() {
    onChange({ type: "remote", url: remoteUrl, apiKey: remoteApiKey || undefined });
  }

  async function testConnection() {
    if (!remoteUrl) return;
    setTestingConnection(true);
    setRemoteConnected(null);
    try {
      const tempClient = new ForgeClient(remoteUrl);
      const healthy = await tempClient.healthCheck();
      setRemoteConnected(healthy);
      if (healthy) {
        onChange({ type: "remote", url: remoteUrl, apiKey: remoteApiKey || undefined });
      }
    } catch {
      setRemoteConnected(false);
    } finally {
      setTestingConnection(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <h4 className="text-sm font-medium text-gray-300">Deploy Target</h4>

      {/* Local */}
      <Card
        hoverable
        className={value.type === "local" ? "border-cyan-500" : ""}
        onClick={selectLocal}
      >
        <div className="flex items-center justify-between">
          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium text-gray-100">Local</span>
            <span className="text-xs text-gray-500">{nodeUrl}</span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${connected ? "bg-green-400" : "bg-gray-600"}`}
            />
            <span className="text-xs text-gray-500">
              {connected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>
      </Card>

      {/* Remote */}
      <Card
        hoverable
        className={value.type === "remote" ? "border-cyan-500" : ""}
        onClick={selectRemote}
      >
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-100">Remote Node</span>
            {remoteConnected === true && (
              <Badge variant="success">Connected</Badge>
            )}
            {remoteConnected === false && (
              <Badge variant="danger">Failed</Badge>
            )}
          </div>
          <Input
            placeholder="https://node.example.com"
            value={remoteUrl}
            onChange={(e) => {
              setRemoteUrl(e.target.value);
              setRemoteConnected(null);
            }}
            onClick={(e) => e.stopPropagation()}
          />
          <Input
            placeholder="API Key (optional)"
            type="password"
            value={remoteApiKey}
            onChange={(e) => setRemoteApiKey(e.target.value)}
            onClick={(e) => e.stopPropagation()}
          />
          <Button
            variant="secondary"
            className="self-start text-sm"
            onClick={(e) => {
              e.stopPropagation();
              testConnection();
            }}
            disabled={!remoteUrl || testingConnection}
          >
            {testingConnection ? "Testing..." : "Test Connection"}
          </Button>
        </div>
      </Card>

      {/* Nexus (Cloud) */}
      <Card className="relative opacity-60 cursor-not-allowed">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-gray-100">Nexus (Cloud)</span>
          <Badge variant="warning">Coming Soon</Badge>
        </div>
      </Card>
    </div>
  );
}
