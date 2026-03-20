import { useAgentEditorStore } from "../../stores/agent";
import { Toggle } from "../ui/Toggle";
import { Select } from "../ui/Select";
import { Input } from "../ui/Input";
import { Button } from "../ui/Button";
import type { MemoryConfig, GuardrailConfig } from "../../types/agent";

const MEMORY_BACKENDS = [
  { value: "in_memory", label: "In-Memory" },
  { value: "redis", label: "Redis" },
  { value: "postgres", label: "PostgreSQL" },
  { value: "chromadb", label: "ChromaDB" },
];

const MEMORY_STRATEGIES = [
  { value: "sliding_window", label: "Sliding Window" },
  { value: "summary", label: "Summary" },
  { value: "token_budget", label: "Token Budget" },
];

const GUARDRAIL_TYPES = [
  { value: "pii_detection", label: "PII Detection" },
  { value: "max_length", label: "Max Length" },
  { value: "cost_limit", label: "Cost Limit" },
  { value: "content_filter", label: "Content Filter" },
  { value: "topic_filter", label: "Topic Filter" },
];

const GUARDRAIL_ACTIONS = [
  { value: "redact", label: "Redact" },
  { value: "block", label: "Block" },
];

type MemoryType = "conversational" | "semantic" | "episodic";

const MEMORY_TYPES: MemoryType[] = ["conversational", "semantic", "episodic"];

function MemorySection({
  type,
  mem,
  onChange,
  onToggle,
  enabled,
}: {
  type: MemoryType;
  mem: MemoryConfig | undefined;
  onChange: (m: MemoryConfig) => void;
  onToggle: (enabled: boolean) => void;
  enabled: boolean;
}) {
  const label = type.charAt(0).toUpperCase() + type.slice(1);
  return (
    <div className="space-y-3">
      <Toggle label={`${label} Memory`} checked={enabled} onChange={onToggle} />
      {enabled && mem && (
        <div className="pl-4 border-l-2 border-gray-700 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Backend"
              id={`${type}-backend`}
              options={MEMORY_BACKENDS}
              value={mem.backend}
              onChange={(e) => onChange({ ...mem, backend: e.target.value })}
            />
            <Select
              label="Strategy"
              id={`${type}-strategy`}
              options={MEMORY_STRATEGIES}
              value={mem.strategy || "sliding_window"}
              onChange={(e) => onChange({ ...mem, strategy: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Max Turns"
              id={`${type}-max-turns`}
              type="number"
              value={mem.max_turns ?? ""}
              onChange={(e) =>
                onChange({
                  ...mem,
                  max_turns: e.target.value
                    ? parseInt(e.target.value, 10)
                    : undefined,
                })
              }
              placeholder="50"
            />
            <Input
              label="TTL (seconds)"
              id={`${type}-ttl`}
              type="number"
              value={mem.ttl ?? ""}
              onChange={(e) =>
                onChange({
                  ...mem,
                  ttl: e.target.value
                    ? parseInt(e.target.value, 10)
                    : undefined,
                })
              }
              placeholder="3600"
            />
          </div>
        </div>
      )}
    </div>
  );
}

function GuardrailsList({
  title,
  guardrails,
  onChange,
}: {
  title: string;
  guardrails: GuardrailConfig[];
  onChange: (g: GuardrailConfig[]) => void;
}) {
  function addGuardrail() {
    onChange([...guardrails, { type: "content_filter", action: "block" }]);
  }

  function removeGuardrail(index: number) {
    onChange(guardrails.filter((_, i) => i !== index));
  }

  function updateGuardrail(index: number, updates: Partial<GuardrailConfig>) {
    onChange(
      guardrails.map((g, i) => (i === index ? { ...g, ...updates } : g))
    );
  }

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium text-gray-300">{title}</h4>
      {guardrails.map((g, i) => (
        <div key={i} className="flex items-end gap-2">
          <Select
            label="Type"
            id={`${title}-${i}-type`}
            options={GUARDRAIL_TYPES}
            value={g.type}
            onChange={(e) => updateGuardrail(i, { type: e.target.value })}
          />
          <Select
            label="Action"
            id={`${title}-${i}-action`}
            options={GUARDRAIL_ACTIONS}
            value={g.action || "block"}
            onChange={(e) =>
              updateGuardrail(i, {
                action: e.target.value as "redact" | "block",
              })
            }
          />
          <Button
            variant="danger"
            className="px-2 py-2 text-sm"
            onClick={() => removeGuardrail(i)}
          >
            Remove
          </Button>
        </div>
      ))}
      <Button variant="secondary" className="text-sm" onClick={addGuardrail}>
        Add guardrail
      </Button>
    </div>
  );
}

export function StepSettings() {
  const config = useAgentEditorStore((s) => s.config);
  const updateSpec = useAgentEditorStore((s) => s.updateSpec);

  const memory = config.spec.memory || {};
  const guardrails = config.spec.guardrails || {};

  function updateMemory(
    type: MemoryType,
    value: MemoryConfig | undefined
  ) {
    const updated = { ...memory };
    if (value) {
      updated[type] = value;
    } else {
      delete updated[type];
    }
    updateSpec("memory", Object.keys(updated).length > 0 ? updated : undefined);
  }

  function updateGuardrails(
    side: "input" | "output",
    value: GuardrailConfig[]
  ) {
    const updated = { ...guardrails, [side]: value };
    if (updated.input?.length === 0) delete updated.input;
    if (updated.output?.length === 0) delete updated.output;
    updateSpec(
      "guardrails",
      Object.keys(updated).length > 0 ? updated : undefined
    );
  }

  return (
    <div className="space-y-8">
      <h2 className="text-xl font-semibold text-gray-100">Settings</h2>

      {/* Memory */}
      <div className="space-y-4">
        <h3 className="text-md font-medium text-gray-200">Memory</h3>
        {MEMORY_TYPES.map((type) => (
          <MemorySection
            key={type}
            type={type}
            enabled={!!memory[type]}
            mem={memory[type]}
            onToggle={(enabled) => {
              if (enabled) {
                updateMemory(type, {
                  backend: "in_memory",
                  strategy: "sliding_window",
                });
              } else {
                updateMemory(type, undefined);
              }
            }}
            onChange={(m) => updateMemory(type, m)}
          />
        ))}
      </div>

      {/* Guardrails */}
      <div className="space-y-4 border-t border-gray-700 pt-6">
        <h3 className="text-md font-medium text-gray-200">Guardrails</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <GuardrailsList
            title="Input Guardrails"
            guardrails={guardrails.input || []}
            onChange={(g) => updateGuardrails("input", g)}
          />
          <GuardrailsList
            title="Output Guardrails"
            guardrails={guardrails.output || []}
            onChange={(g) => updateGuardrails("output", g)}
          />
        </div>
      </div>
    </div>
  );
}
