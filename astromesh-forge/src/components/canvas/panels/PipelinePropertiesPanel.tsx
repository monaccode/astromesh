import { useEffect, useState } from "react";
import type { Node } from "@xyflow/react";
import type { PipelineNodeData } from "../../../types/canvas";
import type { GuardrailConfig, MemoryConfig, ModelConfig, ToolConfig } from "../../../types/agent";
import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";
import { Select } from "../../ui/Select";
import { GuardrailRuleFields } from "../../guardrails/GuardrailRuleFields";
import { memoryBackendOptions, withConnectionUrl } from "../../../data/pipeline-presets";
import { applyToolEdit, readsDescription, toolTypeOptions } from "../../../utils/tools";
import {
  A2A_MAX_BYTES,
  A2A_MAX_TIMEOUT,
  A2A_PARTS,
  a2aFormFrom,
  applyA2AForm,
  validateA2A,
  type A2AErrors,
  type A2AForm,
} from "../../../utils/a2a";
import { modelNodeLabel, candidateSource, providerOptions, withSource } from "../../../utils/model";

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
    // Syncs props into local form state; the idiomatic fix is remounting via `key` or
    // deriving during render. Deferred: this component has no test coverage, see the
    // hook-refactor spec.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncs props into local state
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
    provider: candidateSource(c),
    model: c.model ?? "",
    endpoint: c.endpoint ?? "",
    temperature: c.parameters?.temperature ?? 0.7,
  });

  useEffect(() => {
    const nc = d.config as unknown as ModelConfig;
    // Syncs props into local form state; the idiomatic fix is remounting via `key` or
    // deriving during render. Deferred: this component has no test coverage, see the
    // hook-refactor spec.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncs props into local state
    setLocal({
      provider: candidateSource(nc),
      model: nc.model ?? "",
      endpoint: nc.endpoint ?? "",
      temperature: nc.parameters?.temperature ?? 0.7,
    });
  }, [nodeKey, d.config]);

  function push() {
    // Spread the original block: keys this panel does not edit must survive.
    const next: ModelConfig = {
      ...withSource(c, local.provider),
      model: local.model,
      endpoint: local.endpoint || undefined,
      parameters: { ...c.parameters, temperature: local.temperature },
    };
    const label = modelNodeLabel(nodeKey, next);
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
        options={providerOptions(local.provider)}
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
    type: c.type ?? "builtin",
    agent: c.agent ?? "",
    description: c.description ?? "",
    max_result_tokens: c.max_result_tokens,
  });
  const [a2a, setA2a] = useState<A2AForm>(() => a2aFormFrom(c));
  const [errors, setErrors] = useState<A2AErrors>({});

  useEffect(() => {
    const nc = d.config as unknown as ToolConfig;
    // Syncs props into local form state; the idiomatic fix is remounting via `key` or
    // deriving during render. Deferred: this component has no test coverage, see the
    // hook-refactor spec.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncs props into local state
    setLocal({
      name: nc.name ?? "",
      type: nc.type ?? "builtin",
      agent: nc.agent ?? "",
      description: nc.description ?? "",
      max_result_tokens: nc.max_result_tokens,
    });
    setA2a(a2aFormFrom(nc));
    setErrors({});
  }, [nodeId, d.config]);

  function push() {
    // Spread the original: connection, actions, rate_limit, api/mcp manifests… must survive.
    let next = applyToolEdit(c, local);
    if (local.type === "a2a") {
      // Same checks core runs at bootstrap: an invalid a2a tool never reaches the YAML.
      const errs = validateA2A(local.name, a2a);
      setErrors(errs);
      if (Object.keys(errs).length) return;
      next = applyA2AForm(next, a2a);
    }
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
      {local.type === "a2a" && <FieldError msg={errors.name} />}
      <Select
        label="Type"
        id="t-type"
        options={toolTypeOptions(c.type)}
        value={local.type}
        onChange={(e) =>
          setLocal((s) => ({ ...s, type: e.target.value as ToolConfig["type"] }))
        }
      />
      {local.type === "agent" && (
        <Input
          label="Agent to invoke"
          id="t-agent"
          value={local.agent}
          placeholder={local.name}
          onChange={(e) => setLocal((s) => ({ ...s, agent: e.target.value }))}
        />
      )}
      {local.type === "a2a" && <A2AFields form={a2a} errors={errors} onChange={setA2a} />}
      <Input
        label="Max result tokens (optional)"
        id="t-mrt"
        type="number"
        min={1}
        value={local.max_result_tokens ?? ""}
        onChange={(e) =>
          setLocal((s) => ({
            ...s,
            max_result_tokens: e.target.value ? Number(e.target.value) : undefined,
          }))
        }
      />
      {readsDescription(local.type) && (
        <div className="flex flex-col gap-1">
          <label htmlFor="t-desc" className="text-xs text-gray-500">
            Description{local.type === "a2a" ? " (optional)" : ""}
          </label>
          <textarea
            id="t-desc"
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 min-h-[80px]"
            placeholder={
              local.type === "a2a" ? "Taken from the remote agent's card if empty" : undefined
            }
            value={local.description}
            onChange={(e) => setLocal((s) => ({ ...s, description: e.target.value }))}
          />
        </div>
      )}
      <Button variant="primary" className="w-full text-sm" onClick={push}>
        Apply
      </Button>
    </div>
  );
}

function FieldError({ msg }: { msg?: string }) {
  return msg ? <p className="text-xs text-red-400 -mt-2">{msg}</p> : null;
}

const AUTH_OPTIONS = [
  { value: "none", label: "None" },
  { value: "api_key_env", label: "API key (environment variable)" },
  { value: "bearer_env", label: "Bearer token (environment variable)" },
];

/** `type: a2a` keys: card_url, auth (env var NAME, never the secret) and optional policy. */
function A2AFields({
  form,
  errors,
  onChange,
}: {
  form: A2AForm;
  errors: A2AErrors;
  onChange: (f: A2AForm) => void;
}) {
  const set = (patch: Partial<A2AForm>) => onChange({ ...form, ...patch });
  return (
    <div className="space-y-3">
      <Input
        label="Agent card URL"
        id="t-a2a-card"
        value={form.card_url}
        placeholder="https://agents.example.com/.well-known/agent-card.json"
        onChange={(e) => set({ card_url: e.target.value })}
      />
      <FieldError msg={errors.card_url} />
      <Select
        label="Auth"
        id="t-a2a-auth"
        options={AUTH_OPTIONS}
        value={form.authKind}
        onChange={(e) => set({ authKind: e.target.value as A2AForm["authKind"] })}
      />
      {form.authKind !== "none" && (
        <>
          <Input
            label={
              form.authKind === "api_key_env"
                ? "API key environment variable name"
                : "Bearer token environment variable name"
            }
            id="t-a2a-env"
            value={form.authEnv}
            placeholder="REMOTE_AGENT_TOKEN"
            onChange={(e) => set({ authEnv: e.target.value })}
          />
          <p className="text-xs text-gray-500 -mt-2">
            The name of the variable only; the secret stays in the runtime&apos;s environment.
          </p>
          <FieldError msg={errors.authEnv} />
        </>
      )}
      <p className="text-xs text-gray-500 uppercase tracking-wider pt-1">Policy (optional)</p>
      <Input
        label="Max response bytes"
        id="t-a2a-maxb"
        type="number"
        min={1}
        max={A2A_MAX_BYTES}
        step={1}
        value={form.max_bytes}
        placeholder="1048576"
        onChange={(e) => set({ max_bytes: e.target.value })}
      />
      <FieldError msg={errors.max_bytes} />
      <Input
        label="Timeout (seconds)"
        id="t-a2a-timeout"
        type="number"
        min={0}
        max={A2A_MAX_TIMEOUT}
        value={form.timeout}
        placeholder="60"
        onChange={(e) => set({ timeout: e.target.value })}
      />
      <FieldError msg={errors.timeout} />
      <div className="flex flex-col gap-1">
        <span className="text-sm text-gray-400">Accepted parts</span>
        <div className="flex gap-4">
          {A2A_PARTS.map((part) => (
            <label key={part} className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                className="accent-cyan-500"
                checked={form.accept_parts.includes(part)}
                onChange={(e) =>
                  set({
                    accept_parts: A2A_PARTS.filter((x) =>
                      x === part ? e.target.checked : form.accept_parts.includes(x),
                    ),
                  })
                }
              />
              {part}
            </label>
          ))}
        </div>
        <p className="text-xs text-gray-500">None checked: runtime default (text, data).</p>
      </div>
      <label className="flex items-center gap-2 text-sm text-gray-300">
        <input
          type="checkbox"
          className="accent-cyan-500"
          checked={form.allow_insecure_http}
          onChange={(e) => set({ allow_insecure_http: e.target.checked })}
        />
        Allow insecure http (local development)
      </label>
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
    url: c.connection?.url ?? "",
    strategy: c.strategy ?? "",
    max_turns: c.max_turns ?? 20,
    max_results: c.max_results ?? 8,
    similarity_threshold: c.similarity_threshold ?? 0.7,
    ttl: c.ttl ?? 86400,
  });

  useEffect(() => {
    const nc = d.config as unknown as MemoryConfig;
    // Syncs props into local form state; the idiomatic fix is remounting via `key` or
    // deriving during render. Deferred: this component has no test coverage, see the
    // hook-refactor spec.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncs props into local state
    setLocal({
      backend: nc.backend ?? "redis",
      url: nc.connection?.url ?? "",
      strategy: nc.strategy ?? "",
      max_turns: nc.max_turns ?? 20,
      max_results: nc.max_results ?? 8,
      similarity_threshold: nc.similarity_threshold ?? 0.7,
      ttl: nc.ttl ?? 86400,
    });
  }, [nodeId, d.config]);

  function push() {
    const next: MemoryConfig = {
      ...c,
      backend: local.backend,
      connection: withConnectionUrl(c.connection, local.url),
      strategy: local.strategy || undefined,
      max_turns: local.max_turns,
      max_results: local.max_results,
      similarity_threshold: local.similarity_threshold,
      ttl: local.ttl,
    };
    if (!next.connection) delete next.connection;
    onApply(nodeId, { ...d, config: { ...next } as unknown as Record<string, unknown> });
  }

  return (
    <div className="space-y-3">
      <Select
        label="Backend"
        id="mem-back"
        options={memoryBackendOptions(local.backend)}
        value={local.backend}
        onChange={(e) => setLocal((s) => ({ ...s, backend: e.target.value }))}
      />
      <Input
        label="Connection URL"
        id="mem-url"
        value={local.url}
        onChange={(e) => setLocal((s) => ({ ...s, url: e.target.value }))}
        placeholder="redis://redis:6379/0"
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
  const side = nodeId.startsWith("ig-") ? "input" : "output";
  const [rule, setRule] = useState(d.config as unknown as GuardrailConfig);

  useEffect(() => {
    // Syncs props into local form state; the idiomatic fix is remounting via `key` or
    // deriving during render. Deferred: this component has no test coverage, see the
    // hook-refactor spec.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncs props into local state
    setRule(d.config as unknown as GuardrailConfig);
  }, [nodeId, d.config]);

  function push() {
    onApply(nodeId, {
      ...d,
      label: `${side === "input" ? "Input" : "Output"}: ${rule.type}`,
      config: { ...rule } as unknown as Record<string, unknown>,
    });
  }

  return (
    <div className="space-y-3">
      <GuardrailRuleFields
        key={nodeId}
        idPrefix="g"
        side={side}
        rule={rule}
        onChange={setRule}
      />
      <Button variant="primary" className="w-full text-sm" onClick={push}>
        Apply
      </Button>
    </div>
  );
}
