import { useAgentEditorStore } from "../../stores/agent";
import { Toggle } from "../ui/Toggle";
import { Select } from "../ui/Select";
import { Input } from "../ui/Input";
import { Button } from "../ui/Button";
import type { MemoryConfig, GuardrailConfig } from "../../types/agent";
import { DEFAULT_CONVERSATIONAL, memoryBackendOptions } from "../../data/pipeline-presets";
import { GuardrailRuleFields } from "../guardrails/GuardrailRuleFields";
import { defaultGuardrail, guardrailTypesFor, type GuardrailSide } from "../../utils/guardrails";


const MEMORY_STRATEGIES = [
  { value: "sliding_window", label: "Sliding Window" },
  { value: "summary", label: "Summary" },
  { value: "token_budget", label: "Token Budget" },
];

type MemoryType = "conversational" | "semantic" | "episodic";

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
              options={memoryBackendOptions(mem.backend)}
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
          <Input
            label="Connection URL"
            id={`${type}-connection-url`}
            value={mem.connection?.url ?? ""}
            onChange={(e) =>
              onChange({ ...mem, connection: { ...mem.connection, url: e.target.value } })
            }
            placeholder="redis://redis:6379/0"
          />
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
  side,
  guardrails,
  onChange,
}: {
  title: string;
  side: GuardrailSide;
  guardrails: GuardrailConfig[];
  onChange: (g: GuardrailConfig[]) => void;
}) {
  function addGuardrail() {
    onChange([...guardrails, defaultGuardrail(guardrailTypesFor(side)[0])]);
  }

  function removeGuardrail(index: number) {
    onChange(guardrails.filter((_, i) => i !== index));
  }

  function updateGuardrail(index: number, rule: GuardrailConfig) {
    onChange(guardrails.map((g, i) => (i === index ? rule : g)));
  }

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium text-gray-300">{title}</h4>
      {guardrails.map((g, i) => (
        <div key={i} className="flex items-start gap-2">
          <div className="flex-1">
            <GuardrailRuleFields
              idPrefix={`${title}-${i}`}
              side={side}
              rule={g}
              onChange={(r) => updateGuardrail(i, r)}
            />
          </div>
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
        <MemorySection
          type="conversational"
          enabled={!!memory.conversational}
          mem={memory.conversational}
          onToggle={(enabled) =>
            updateMemory("conversational", enabled ? { ...DEFAULT_CONVERSATIONAL } : undefined)
          }
          onChange={(m) => updateMemory("conversational", m)}
        />
        {memory.semantic && (
          <p className="text-xs text-gray-400">
            Semantic memory: {memory.semantic.backend}, embeddings{" "}
            {memory.semantic.embeddings ? "set" : "missing"}. Kept unchanged.
          </p>
        )}
        {memory.semantic && !memory.semantic.embeddings && (
          <p className="text-xs text-amber-400">
            memory.semantic needs embeddings: the runtime does not load the agent without them.
          </p>
        )}
        {memory.episodic && (
          <p className="text-xs text-gray-400">
            Episodic memory: {memory.episodic.backend}. Kept unchanged.
          </p>
        )}
      </div>

      {/* Guardrails */}
      <div className="space-y-4 border-t border-gray-700 pt-6">
        <h3 className="text-md font-medium text-gray-200">Guardrails</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <GuardrailsList
            title="Input Guardrails"
            side="input"
            guardrails={guardrails.input || []}
            onChange={(g) => updateGuardrails("input", g)}
          />
          <GuardrailsList
            title="Output Guardrails"
            side="output"
            guardrails={guardrails.output || []}
            onChange={(g) => updateGuardrails("output", g)}
          />
        </div>
      </div>
    </div>
  );
}
