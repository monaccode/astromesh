import { useAgentEditorStore } from "../../stores/agent";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";
import { Toggle } from "../ui/Toggle";
import type { ModelConfig } from "../../types/agent";

const PROVIDERS = [
  { value: "ollama", label: "Ollama" },
  { value: "openai_compat", label: "OpenAI Compatible" },
  { value: "vllm", label: "vLLM" },
  { value: "llamacpp", label: "llama.cpp" },
  { value: "hf_tgi", label: "HuggingFace TGI" },
  { value: "onnx", label: "ONNX" },
];

const ROUTING_STRATEGIES = [
  { value: "cost_optimized", label: "Cost Optimized" },
  { value: "latency_optimized", label: "Latency Optimized" },
  { value: "quality_first", label: "Quality First" },
  { value: "round_robin", label: "Round Robin" },
];

function ModelFields({
  title,
  model,
  onChange,
}: {
  title: string;
  model: ModelConfig;
  onChange: (m: ModelConfig) => void;
}) {
  return (
    <div className="space-y-4">
      <h3 className="text-md font-medium text-gray-200">{title}</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Select
          label="Provider"
          id={`${title}-provider`}
          options={PROVIDERS}
          value={model.provider}
          onChange={(e) => onChange({ ...model, provider: e.target.value })}
        />
        <Input
          label="Model"
          id={`${title}-model`}
          value={model.model}
          onChange={(e) => onChange({ ...model, model: e.target.value })}
          placeholder="llama3.1:8b"
        />
        <Input
          label="Endpoint"
          id={`${title}-endpoint`}
          value={model.endpoint || ""}
          onChange={(e) => onChange({ ...model, endpoint: e.target.value })}
          placeholder="http://ollama:11434"
        />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
            onChange={(e) =>
              onChange({
                ...model,
                parameters: {
                  ...model.parameters,
                  temperature: parseFloat(e.target.value),
                },
              })
            }
            className="accent-cyan-500"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm text-gray-400">
            Top P: {model.parameters?.top_p ?? 1.0}
          </label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={model.parameters?.top_p ?? 1.0}
            onChange={(e) =>
              onChange({
                ...model,
                parameters: {
                  ...model.parameters,
                  top_p: parseFloat(e.target.value),
                },
              })
            }
            className="accent-cyan-500"
          />
        </div>
        <Input
          label="Max Tokens"
          id={`${title}-max-tokens`}
          type="number"
          value={model.parameters?.max_tokens ?? ""}
          onChange={(e) =>
            onChange({
              ...model,
              parameters: {
                ...model.parameters,
                max_tokens: e.target.value ? parseInt(e.target.value, 10) : undefined,
              },
            })
          }
          placeholder="4096"
        />
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

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-gray-100">Model Configuration</h2>

      <ModelFields
        title="Primary Model"
        model={modelSpec.primary}
        onChange={(primary) => updateModel({ primary })}
      />

      <div className="border-t border-gray-700 pt-4">
        <Toggle
          label="Enable Fallback Model"
          checked={hasFallback}
          onChange={(checked) => {
            if (checked) {
              updateModel({
                fallback: {
                  provider: "ollama",
                  model: "",
                  endpoint: "",
                },
              });
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
