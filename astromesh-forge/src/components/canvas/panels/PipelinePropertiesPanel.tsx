import { useEffect, useState } from "react";
import type { Node } from "@xyflow/react";
import type { PipelineNodeData } from "../../../types/canvas";
import type { GuardrailConfig, MemoryConfig, ModelConfig, ToolConfig } from "../../../types/agent";
import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";
import { Select } from "../../ui/Select";

const PROVIDERS = [
  { value: "ollama", label: "Ollama" },
  { value: "openai_compat", label: "OpenAI compatible" },
  { value: "vllm", label: "vLLM" },
  { value: "llamacpp", label: "llama.cpp" },
];

const TOOL_TYPES: { value: ToolConfig["type"]; label: string }[] = [
  { value: "internal", label: "Internal / built-in" },
  { value: "rag", label: "RAG / knowledge" },
  { value: "mcp", label: "MCP" },
  { value: "webhook", label: "Webhook (HTTP)" },
  { value: "agent", label: "Sub-agent" },
];

const MEMORY_BACKENDS = [
  { value: "redis", label: "Redis" },
  { value: "postgres", label: "PostgreSQL" },
  { value: "chromadb", label: "ChromaDB" },
  { value: "sqlite", label: "SQLite" },
  { value: "in_memory", label: "In-memory" },
];

interface PipelinePropertiesPanelProps {
  node: Node | null;
  onApply: (id: string, data: PipelineNodeData) => void;
  onRemove: (id: string) => void;
  onClose: () => void;
}

export function PipelinePropertiesPanel({
  node,
  onApply,
  onRemove,
  onClose,
}: PipelinePropertiesPanelProps) {
  if (!node) return null;

  const d = node.data as PipelineNodeData;
  const cat = node.type ?? d.category;

  return (
    <div className="w-[320px] bg-gray-900 border-l border-gray-800 h-full overflow-y-auto shrink-0 flex flex-col">
      <div className="p-3 border-b border-gray-800 flex items-center justify-between shrink-0">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Edit block
        </h2>
        <button
          type="button"
          className="text-gray-500 hover:text-gray-300 text-lg leading-none"
          onClick={onClose}
        >
          &times;
        </button>
      </div>

      <div className="p-4 space-y-4 flex-1">
        <p className="text-xs text-gray-500">
          Adjust fields and click Apply, then use &quot;Save pipeline&quot; to persist on the
          server.
        </p>

        {cat === "prompt" && <PromptFields nodeId={node.id} d={d} onApply={onApply} />}
        {cat === "model" && (
          <ModelFields nodeId={node.id} nodeKey={node.id} d={d} onApply={onApply} />
        )}
        {cat === "tool" && <ToolFields nodeId={node.id} d={d} onApply={onApply} />}
        {cat === "memory" && <MemoryFields nodeId={node.id} d={d} onApply={onApply} />}
        {cat === "guardrail" && <GuardrailFields nodeId={node.id} d={d} onApply={onApply} />}
        {!["prompt", "model", "tool", "memory", "guardrail"].includes(cat) && (
          <p className="text-sm text-gray-500">No editor for this node type.</p>
        )}
      </div>

      <div className="p-4 border-t border-gray-800 space-y-2 shrink-0">
        <Button
          variant="danger"
          className="w-full text-sm py-1.5"
          onClick={() => onRemove(node.id)}
        >
          Remove from pipeline
        </Button>
      </div>
    </div>
  );
}

function PromptFields({
  nodeId,
  d,
  onApply,
}: {
  nodeId: string;
  d: PipelineNodeData;
  onApply: (id: string, data: PipelineNodeData) => void;
}) {
  const [text, setText] = useState(String(d.config.system ?? ""));
  useEffect(() => {
    setText(String(d.config.system ?? ""));
  }, [nodeId, d.config]);

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-500">System prompt</label>
        <textarea
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 min-h-[200px]"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </div>
      <Button
        variant="primary"
        className="w-full text-sm"
        onClick={() =>
          onApply(nodeId, {
            ...d,
            config: { ...d.config, system: text },
          })
        }
      >
        Apply
      </Button>
    </div>
  );
}

function ModelFields({
  nodeId,
  nodeKey,
  d,
  onApply,
}: {
  nodeId: string;
  nodeKey: string;
  d: PipelineNodeData;
  onApply: (id: string, data: PipelineNodeData) => void;
}) {
  const c = d.config as unknown as ModelConfig;
  const [local, setLocal] = useState({
    provider: c.provider ?? "ollama",
    model: c.model ?? "",
    endpoint: c.endpoint ?? "",
    temperature: c.parameters?.temperature ?? 0.7,
  });

  useEffect(() => {
    const nc = d.config as unknown as ModelConfig;
    setLocal({
      provider: nc.provider ?? "ollama",
      model: nc.model ?? "",
      endpoint: nc.endpoint ?? "",
      temperature: nc.parameters?.temperature ?? 0.7,
    });
  }, [nodeKey, d.config]);

  function push() {
    const next: ModelConfig = {
      provider: local.provider,
      model: local.model,
      endpoint: local.endpoint || undefined,
      parameters: { temperature: local.temperature },
    };
    const label =
      nodeKey === "model-fallback"
        ? `Fallback: ${next.provider}/${next.model}`
        : `${next.provider}/${next.model}`;
    onApply(nodeId, {
      ...d,
      label,
      config: { ...next } as unknown as Record<string, unknown>,
    });
  }

  return (
    <div className="space-y-3">
      <Select
        label="Provider"
        id="m-prov"
        options={PROVIDERS}
        value={local.provider}
        onChange={(e) => setLocal((s) => ({ ...s, provider: e.target.value }))}
      />
      <Input
        label="Model name"
        id="m-model"
        value={local.model}
        onChange={(e) => setLocal((s) => ({ ...s, model: e.target.value }))}
      />
      <Input
        label="Endpoint (optional)"
        id="m-end"
        value={local.endpoint}
        onChange={(e) => setLocal((s) => ({ ...s, endpoint: e.target.value }))}
        placeholder="http://127.0.0.1:11434"
      />
      <Input
        label="Temperature"
        id="m-temp"
        type="number"
        step={0.05}
        min={0}
        max={2}
        value={String(local.temperature)}
        onChange={(e) =>
          setLocal((s) => ({ ...s, temperature: Number(e.target.value) || 0 }))
        }
      />
      <Button variant="primary" className="w-full text-sm" onClick={push}>
        Apply
      </Button>
    </div>
  );
}

function ToolFields({
  nodeId,
  d,
  onApply,
}: {
  nodeId: string;
  d: PipelineNodeData;
  onApply: (id: string, data: PipelineNodeData) => void;
}) {
  const c = d.config as unknown as ToolConfig;
  const [local, setLocal] = useState({
    name: c.name ?? "",
    type: c.type ?? "internal",
    description: c.description ?? "",
  });

  useEffect(() => {
    const nc = d.config as unknown as ToolConfig;
    setLocal({
      name: nc.name ?? "",
      type: nc.type ?? "internal",
      description: nc.description ?? "",
    });
  }, [nodeId, d.config]);

  function push() {
    const next: ToolConfig = {
      name: local.name,
      type: local.type,
      description: local.description,
      parameters: c.parameters,
    };
    onApply(nodeId, {
      ...d,
      label: next.name,
      config: { ...next } as unknown as Record<string, unknown>,
    });
  }

  return (
    <div className="space-y-3">
      <Input
        label="Tool name"
        id="t-name"
        value={local.name}
        onChange={(e) => setLocal((s) => ({ ...s, name: e.target.value }))}
      />
      <Select
        label="Type"
        id="t-type"
        options={TOOL_TYPES}
        value={local.type}
        onChange={(e) =>
          setLocal((s) => ({ ...s, type: e.target.value as ToolConfig["type"] }))
        }
      />
      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-500">Description</label>
        <textarea
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 min-h-[80px]"
          value={local.description}
          onChange={(e) => setLocal((s) => ({ ...s, description: e.target.value }))}
        />
      </div>
      <Button variant="primary" className="w-full text-sm" onClick={push}>
        Apply
      </Button>
    </div>
  );
}

function MemoryFields({
  nodeId,
  d,
  onApply,
}: {
  nodeId: string;
  d: PipelineNodeData;
  onApply: (id: string, data: PipelineNodeData) => void;
}) {
  const c = d.config as unknown as MemoryConfig;
  const [local, setLocal] = useState({
    backend: c.backend ?? "redis",
    strategy: c.strategy ?? "",
    max_turns: c.max_turns ?? 20,
    max_results: c.max_results ?? 8,
    similarity_threshold: c.similarity_threshold ?? 0.7,
    ttl: c.ttl ?? 86400,
  });

  useEffect(() => {
    const nc = d.config as unknown as MemoryConfig;
    setLocal({
      backend: nc.backend ?? "redis",
      strategy: nc.strategy ?? "",
      max_turns: nc.max_turns ?? 20,
      max_results: nc.max_results ?? 8,
      similarity_threshold: nc.similarity_threshold ?? 0.7,
      ttl: nc.ttl ?? 86400,
    });
  }, [nodeId, d.config]);

  function push() {
    const next: MemoryConfig = {
      backend: local.backend,
      strategy: local.strategy || undefined,
      max_turns: local.max_turns,
      max_results: local.max_results,
      similarity_threshold: local.similarity_threshold,
      ttl: local.ttl,
    };
    onApply(nodeId, { ...d, config: { ...next } as unknown as Record<string, unknown> });
  }

  return (
    <div className="space-y-3">
      <Select
        label="Backend"
        id="mem-back"
        options={MEMORY_BACKENDS}
        value={local.backend}
        onChange={(e) => setLocal((s) => ({ ...s, backend: e.target.value }))}
      />
      <Input
        label="Strategy"
        id="mem-strat"
        value={local.strategy}
        onChange={(e) => setLocal((s) => ({ ...s, strategy: e.target.value }))}
        placeholder="sliding_window, similarity…"
      />
      <Input
        label="Max turns (chat)"
        id="mem-mt"
        type="number"
        value={String(local.max_turns)}
        onChange={(e) => setLocal((s) => ({ ...s, max_turns: Number(e.target.value) }))}
      />
      <Input
        label="Max results (vectors)"
        id="mem-mr"
        type="number"
        value={String(local.max_results)}
        onChange={(e) => setLocal((s) => ({ ...s, max_results: Number(e.target.value) }))}
      />
      <Input
        label="Similarity threshold"
        id="mem-sim"
        type="number"
        step={0.01}
        min={0}
        max={1}
        value={String(local.similarity_threshold)}
        onChange={(e) =>
          setLocal((s) => ({ ...s, similarity_threshold: Number(e.target.value) }))
        }
      />
      <Input
        label="TTL (seconds)"
        id="mem-ttl"
        type="number"
        value={String(local.ttl)}
        onChange={(e) => setLocal((s) => ({ ...s, ttl: Number(e.target.value) }))}
      />
      <Button variant="primary" className="w-full text-sm" onClick={push}>
        Apply
      </Button>
    </div>
  );
}

function GuardrailFields({
  nodeId,
  d,
  onApply,
}: {
  nodeId: string;
  d: PipelineNodeData;
  onApply: (id: string, data: PipelineNodeData) => void;
}) {
  const c = d.config as unknown as GuardrailConfig;
  const [local, setLocal] = useState({
    type: c.type ?? "",
    action: (c.action ?? "block") as NonNullable<GuardrailConfig["action"]>,
  });

  useEffect(() => {
    const nc = d.config as unknown as GuardrailConfig;
    setLocal({
      type: nc.type ?? "",
      action: (nc.action ?? "block") as NonNullable<GuardrailConfig["action"]>,
    });
  }, [nodeId, d.config]);

  function push() {
    const next: GuardrailConfig = { type: local.type, action: local.action };
    const phase = nodeId.startsWith("ig-") ? "Input" : "Output";
    onApply(nodeId, {
      ...d,
      label: `${phase}: ${local.type}`,
      config: { ...next } as unknown as Record<string, unknown>,
    });
  }

  return (
    <div className="space-y-3">
      <Input
        label="Guardrail type"
        id="g-type"
        value={local.type}
        onChange={(e) => setLocal((s) => ({ ...s, type: e.target.value }))}
        placeholder="pii_detection, cost_limit…"
      />
      <Select
        label="Action"
        id="g-act"
        options={[
          { value: "block", label: "Block" },
          { value: "redact", label: "Redact" },
        ]}
        value={local.action}
        onChange={(e) =>
          setLocal((s) => ({
            ...s,
            action: e.target.value as NonNullable<GuardrailConfig["action"]>,
          }))
        }
      />
      <Button variant="primary" className="w-full text-sm" onClick={push}>
        Apply
      </Button>
    </div>
  );
}
