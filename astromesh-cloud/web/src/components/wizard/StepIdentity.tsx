"use client";

import { useWizardStore } from "@/lib/store";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/utils";

const TONE_OPTIONS = [
  {
    id: "professional",
    label: "Professional",
    description: "Formal, precise, and authoritative",
    icon: "💼",
    color: "text-am-cyan",
    bg: "bg-am-cyan-dim",
    border: "border-am-cyan/30",
  },
  {
    id: "casual",
    label: "Casual",
    description: "Friendly, relaxed, and approachable",
    icon: "😊",
    color: "text-am-green",
    bg: "bg-am-green/10",
    border: "border-am-green/30",
  },
  {
    id: "technical",
    label: "Technical",
    description: "Detailed, precise, and data-driven",
    icon: "⚙️",
    color: "text-am-purple",
    bg: "bg-am-purple/10",
    border: "border-am-purple/30",
  },
  {
    id: "empathetic",
    label: "Empathetic",
    description: "Warm, supportive, and understanding",
    icon: "🤝",
    color: "text-am-amber",
    bg: "bg-am-amber/10",
    border: "border-am-amber/30",
  },
];

function toSlug(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-");
}

export function StepIdentity() {
  const config = useWizardStore((s) => s.config);
  const updateConfig = useWizardStore((s) => s.updateConfig);

  function handleDisplayNameChange(value: string) {
    updateConfig({ displayName: value, agentName: toSlug(value) });
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-lg font-semibold text-am-text">Agent Identity</h2>
        <p className="mt-1 text-sm text-am-text-dim">
          Give your agent a name and personality.
        </p>
      </div>

      <div className="space-y-5">
        {/* Display name + auto slug */}
        <Input
          label="Display Name"
          placeholder="Customer Support Bot"
          value={config.displayName}
          onChange={(e) => handleDisplayNameChange(e.target.value)}
        />

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-am-text-dim uppercase tracking-wide">
            Agent Slug
          </label>
          <div className="flex items-center rounded-md bg-am-bg border border-am-border px-3 py-2 text-sm">
            <span className="text-am-text-dim select-none">agents/</span>
            <span className="text-am-cyan font-mono">
              {config.agentName || "your-agent-slug"}
            </span>
          </div>
          <p className="text-xs text-am-text-dim">
            Auto-generated from display name. Used in API calls.
          </p>
        </div>

        {/* System prompt */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-am-text-dim uppercase tracking-wide">
            System Prompt
          </label>
          <textarea
            rows={5}
            placeholder="You are an assistant that..."
            value={config.systemPrompt}
            onChange={(e) => updateConfig({ systemPrompt: e.target.value })}
            className={cn(
              "w-full rounded-md bg-am-bg border border-am-border px-3 py-2 text-sm text-am-text placeholder:text-am-text-dim resize-y",
              "focus:outline-none focus:ring-2 focus:ring-am-cyan focus:border-transparent transition-all"
            )}
          />
        </div>
      </div>

      {/* Tone selector */}
      <div className="space-y-3">
        <p className="text-xs font-medium text-am-text-dim uppercase tracking-wide">
          Tone
        </p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {TONE_OPTIONS.map((tone) => {
            const selected = config.tone === tone.id;
            return (
              <button
                key={tone.id}
                onClick={() => updateConfig({ tone: tone.id })}
                className={cn(
                  "flex flex-col items-center gap-2 rounded-xl border p-4 text-center transition-all",
                  "hover:border-am-border-hover hover:shadow-[0_0_12px_rgba(0,212,255,0.1)]",
                  selected
                    ? "border-am-cyan shadow-[0_0_16px_rgba(0,212,255,0.25)] bg-am-cyan-dim"
                    : "border-am-border bg-am-surface"
                )}
              >
                <span
                  className={cn(
                    "flex h-9 w-9 items-center justify-center rounded-lg text-lg",
                    tone.bg,
                    tone.border,
                    "border"
                  )}
                >
                  {tone.icon}
                </span>
                <span
                  className={cn(
                    "text-sm font-medium",
                    selected ? "text-am-cyan" : "text-am-text"
                  )}
                >
                  {tone.label}
                </span>
                <span className="text-xs text-am-text-dim leading-snug">
                  {tone.description}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
