"use client";

import { useWizardStore } from "@/lib/store";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

interface ModelOption {
  id: string;
  provider: string;
  name: string;
  description: string;
  byok?: boolean;
  icon: string;
}

const FREE_MODELS: ModelOption[] = [
  {
    id: "llama3",
    provider: "Meta",
    name: "Llama 3",
    description: "Fast, capable open-source model for most tasks.",
    icon: "🦙",
  },
  {
    id: "mistral",
    provider: "Mistral AI",
    name: "Mistral 7B",
    description: "Efficient and strong reasoning for its size.",
    icon: "🌪️",
  },
  {
    id: "phi3",
    provider: "Microsoft",
    name: "Phi-3",
    description: "Compact model with surprisingly strong benchmarks.",
    icon: "🔬",
  },
];

const BYOK_MODELS: ModelOption[] = [
  {
    id: "gpt-4o",
    provider: "OpenAI",
    name: "GPT-4o",
    description: "OpenAI's flagship multimodal model.",
    byok: true,
    icon: "✦",
  },
  {
    id: "claude-sonnet",
    provider: "Anthropic",
    name: "Claude Sonnet",
    description: "Balanced intelligence and speed from Anthropic.",
    byok: true,
    icon: "◈",
  },
  {
    id: "gemini-pro",
    provider: "Google",
    name: "Gemini Pro",
    description: "Google's powerful multimodal foundation model.",
    byok: true,
    icon: "◇",
  },
];

const ROUTING_STRATEGIES = [
  {
    id: "cost_optimized",
    label: "Cheapest",
    description: "Minimize token spend. Best for high-volume agents.",
    icon: "💰",
  },
  {
    id: "latency_optimized",
    label: "Fastest",
    description: "Lowest latency. Best for real-time interactions.",
    icon: "⚡",
  },
  {
    id: "quality_first",
    label: "Best Quality",
    description: "Route to highest-capability available model.",
    icon: "🏆",
  },
];

function ModelCard({
  model,
  selected,
  onSelect,
}: {
  model: ModelOption;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        "flex flex-col gap-2 rounded-xl border p-4 text-left transition-all w-full",
        "hover:border-am-border-hover hover:shadow-[0_0_12px_rgba(0,212,255,0.1)]",
        selected
          ? "border-am-cyan shadow-[0_0_16px_rgba(0,212,255,0.25)] bg-am-cyan-dim"
          : "border-am-border bg-am-surface"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-xl leading-none">{model.icon}</span>
        {model.byok && (
          <span className="rounded-full bg-am-amber/10 border border-am-amber/30 px-2 py-0.5 text-xs text-am-amber font-medium whitespace-nowrap">
            Bring your key
          </span>
        )}
      </div>
      <div>
        <p
          className={cn(
            "text-sm font-semibold",
            selected ? "text-am-cyan" : "text-am-text"
          )}
        >
          {model.name}
        </p>
        <p className="text-xs text-am-text-dim">{model.provider}</p>
      </div>
      <p className="text-xs text-am-text-dim leading-snug">{model.description}</p>
    </button>
  );
}

export function StepModel() {
  const config = useWizardStore((s) => s.config);
  const updateConfig = useWizardStore((s) => s.updateConfig);

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-lg font-semibold text-am-text">Model Selection</h2>
        <p className="mt-1 text-sm text-am-text-dim">
          Choose the AI model and routing strategy for your agent.
        </p>
      </div>

      {/* Free models */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-am-text-dim uppercase tracking-wide">
            Included (Free)
          </span>
          <span className="rounded-full bg-am-green/10 border border-am-green/20 px-2 py-0.5 text-xs text-am-green">
            No key required
          </span>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {FREE_MODELS.map((m) => (
            <ModelCard
              key={m.id}
              model={m}
              selected={config.model === m.id}
              onSelect={() => updateConfig({ model: m.id, provider: m.provider.toLowerCase() })}
            />
          ))}
        </div>
      </div>

      {/* BYOK models */}
      <div className="space-y-3">
        <span className="text-xs font-medium text-am-text-dim uppercase tracking-wide">
          BYOK — Bring Your Own Key
        </span>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {BYOK_MODELS.map((m) => (
            <ModelCard
              key={m.id}
              model={m}
              selected={config.model === m.id}
              onSelect={() => updateConfig({ model: m.id, provider: m.provider.toLowerCase() })}
            />
          ))}
        </div>
      </div>

      {/* Routing strategy */}
      <div className="space-y-3">
        <p className="text-xs font-medium text-am-text-dim uppercase tracking-wide">
          Routing Strategy
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {ROUTING_STRATEGIES.map((s) => {
            const selected = config.routingStrategy === s.id;
            return (
              <button
                key={s.id}
                onClick={() => updateConfig({ routingStrategy: s.id })}
                className={cn(
                  "flex flex-col gap-2 rounded-xl border p-4 text-left transition-all",
                  "hover:border-am-border-hover",
                  selected
                    ? "border-am-cyan shadow-[0_0_16px_rgba(0,212,255,0.2)] bg-am-cyan-dim"
                    : "border-am-border bg-am-surface"
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="text-base leading-none">{s.icon}</span>
                  <span
                    className={cn(
                      "text-sm font-semibold",
                      selected ? "text-am-cyan" : "text-am-text"
                    )}
                  >
                    {s.label}
                  </span>
                  {selected && (
                    <span className="ml-auto h-2 w-2 rounded-full bg-am-cyan" />
                  )}
                </div>
                <p className="text-xs text-am-text-dim leading-snug">{s.description}</p>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
