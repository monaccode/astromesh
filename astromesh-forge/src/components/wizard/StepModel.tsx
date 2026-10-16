import { useState } from "react";
import { useAgentEditorStore } from "../../stores/agent";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";
import { Toggle } from "../ui/Toggle";
import type { ModelConfig, ModelRole } from "../../types/agent";
import {
  ROUTING_STRATEGIES,
  candidateSource,
  isRoleShape,
  providerOptions,
  toRoleShape,
  withSource,
} from "../../utils/model";

const num = (v: string) => (v ? Number(v) : undefined);

function ModelFields({
  title,
  model,
  onChange,
}: {
  title: string;
  model: ModelConfig;
  onChange: (m: ModelConfig) => void;
}) {
  const source = candidateSource(model);
  const setParam = (key: string, value: number | undefined) =>
    onChange({ ...model, parameters: { ...model.parameters, [key]: value } });
  return (
    <div className="space-y-4">
      <h3 className="text-md font-medium text-gray-200">{title}</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Select
          label="Provider"
          id={`${title}-provider`}
          options={providerOptions(source)}
          value={source}
          onChange={(e) => onChange(withSource(model, e.target.value))}
        />
        <Input
          label="Model"
          id={`${title}-model`}
          value={model.model ?? ""}
          onChange={(e) => onChange({ ...model, model: e.target.value })}
          placeholder="llama3.1:8b"
        />
        <Input
          label="Endpoint"
          id={`${title}-endpoint`}
          value={model.endpoint || ""}
          onChange={(e) => onChange({ ...model, endpoint: e.target.value || undefined })}
          placeholder="http://ollama:11434"
        />
        <Input
          label="Provider ref (ProviderConfig)"
          id={`${title}-provider-ref`}
          value={model.providerRef ?? ""}
          onChange={(e) => onChange({ ...model, providerRef: e.target.value || undefined })}
          placeholder="gateway-kimi"
        />
        <Input
          label="Context window (tokens)"
          id={`${title}-context-window`}
          type="number"
          value={model.context_window ?? ""}
          onChange={(e) => onChange({ ...model, context_window: num(e.target.value) })}
          placeholder="128000"
        />
        <Input
          label="Max Tokens"
          id={`${title}-max-tokens`}
          type="number"
          value={model.parameters?.max_tokens ?? ""}
          onChange={(e) => setParam("max_tokens", num(e.target.value))}
          placeholder="4096"
        />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="flex flex-col gap-1">
          <label className="text-sm text-gray-400">
            Temperature: {model.parameters?.temperature ?? 0.7}
          </label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={model.parameters?.temperature ?? 0.7}
            onChange={(e) => setParam("temperature", parseFloat(e.target.value))}
            className="accent-cyan-500"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm text-gray-400">Top P: {model.parameters?.top_p ?? 1.0}</label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={model.parameters?.top_p ?? 1.0}
            onChange={(e) => setParam("top_p", parseFloat(e.target.value))}
            className="accent-cyan-500"
          />
        </div>
      </div>
    </div>
  );
}

const NEW_CANDIDATE: ModelConfig = { provider: "ollama", model: "", endpoint: "" };

function RoleEditor({
  name,
  role,
  onChange,
  onRemove,
}: {
  name: string;
  role: ModelRole;
  onChange: (r: ModelRole) => void;
  onRemove?: () => void;
}) {
  const candidates = role.candidates ?? [];
  const setCandidates = (c: ModelConfig[]) => onChange({ ...role, candidates: c });
  return (
    <div className="space-y-4 border border-gray-700 rounded-xl p-4">
      <div className="flex items-end justify-between gap-4">
        <h3 className="text-md font-semibold text-cyan-300">Role: {name}</h3>
        <Select
          label="Strategy"
          id={`role-${name}-strategy`}
          options={ROUTING_STRATEGIES}
          value={role.strategy ?? "cost_optimized"}
          onChange={(e) => onChange({ ...role, strategy: e.target.value })}
        />
        {onRemove && (
          <Button variant="danger" className="text-sm" onClick={onRemove}>
            Remove role
          </Button>
        )}
      </div>
      {candidates.map((c, i) => (
        <div key={i} className="space-y-2">
          <ModelFields
            title={`${name} candidate ${i + 1}`}
            model={c}
            onChange={(m) => setCandidates(candidates.map((x, j) => (j === i ? m : x)))}
          />
          <Button
            variant="ghost"
            className="text-xs"
            onClick={() => setCandidates(candidates.filter((_, j) => j !== i))}
          >
            Remove candidate
          </Button>
        </div>
      ))}
      <Button
        variant="secondary"
        className="text-sm"
        onClick={() => setCandidates([...candidates, { ...NEW_CANDIDATE }])}
      >
        Add candidate
      </Button>
    </div>
  );
}

function RolesEditor() {
  const modelSpec = useAgentEditorStore((s) => s.config.spec.model);
  const updateSpec = useAgentEditorStore((s) => s.updateSpec);
  const [newRole, setNewRole] = useState("");
  const roles = modelSpec.roles ?? {};

  const setRole = (name: string, role: ModelRole) =>
    updateSpec("model", { ...modelSpec, roles: { ...roles, [name]: role } });
  const removeRole = (name: string) => {
    const { [name]: _drop, ...rest } = roles;
    updateSpec("model", { ...modelSpec, roles: rest });
  };

  return (
    <div className="space-y-4">
      <RoleEditor
        name="default"
        role={modelSpec.default ?? { candidates: [] }}
        onChange={(r) => updateSpec("model", { ...modelSpec, default: r })}
      />
      {Object.entries(roles).map(([name, role]) => (
        <RoleEditor
          key={name}
          name={name}
          role={role ?? { candidates: [] }}
          onChange={(r) => setRole(name, r)}
          onRemove={() => removeRole(name)}
        />
      ))}
      <div className="flex items-end gap-2">
        <Input
          label="New role"
          id="new-role"
          value={newRole}
          onChange={(e) => setNewRole(e.target.value.trim())}
          placeholder="planner, summarizer…"
        />
        <Button
          variant="secondary"
          className="text-sm"
          disabled={!newRole || newRole === "default" || newRole in roles}
          onClick={() => {
            setRole(newRole, { candidates: [{ ...NEW_CANDIDATE }], strategy: "cost_optimized" });
            setNewRole("");
          }}
        >
          Add role
        </Button>
      </div>
    </div>
  );
}

export function StepModel() {
  const config = useAgentEditorStore((s) => s.config);
  const updateSpec = useAgentEditorStore((s) => s.updateSpec);

  const modelSpec = config.spec.model;
  const hasFallback = !!modelSpec.fallback;

  function updateModel(updates: Partial<typeof modelSpec>) {
    updateSpec("model", { ...modelSpec, ...updates });
  }

  if (isRoleShape(modelSpec)) {
    return (
      <div className="space-y-6">
        <h2 className="text-xl font-semibold text-gray-100">Model Configuration (per role)</h2>
        <p className="text-sm text-gray-400">
          Map roles to patterns with <code>orchestration.role_map</code>; unmapped steps use{" "}
          <code>default</code>.
        </p>
        <RolesEditor />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-100">Model Configuration</h2>
        <Button
          variant="secondary"
          className="text-sm"
          onClick={() => updateSpec("model", toRoleShape(modelSpec))}
        >
          Use per-role models
        </Button>
      </div>

      <ModelFields
        title="Primary Model"
        model={modelSpec.primary ?? { ...NEW_CANDIDATE }}
        onChange={(primary) => updateModel({ primary })}
      />

      <div className="border-t border-gray-700 pt-4">
        <Toggle
          label="Enable Fallback Model"
          checked={hasFallback}
          onChange={(checked) => {
            if (checked) {
              updateModel({ fallback: { ...NEW_CANDIDATE } });
            } else {
              const { fallback: _, ...rest } = modelSpec;
              updateSpec("model", rest as typeof modelSpec);
            }
          }}
        />
      </div>

      {hasFallback && modelSpec.fallback && (
        <ModelFields
          title="Fallback Model"
          model={modelSpec.fallback}
          onChange={(fallback) => updateModel({ fallback })}
        />
      )}

      <div className="border-t border-gray-700 pt-4">
        <Select
          label="Routing Strategy"
          id="routing-strategy"
          options={ROUTING_STRATEGIES}
          value={modelSpec.routing?.strategy || "cost_optimized"}
          onChange={(e) =>
            updateModel({
              routing: { ...modelSpec.routing, strategy: e.target.value },
            })
          }
        />
      </div>
    </div>
  );
}
