"use client";

import { useWizardStore } from "@/lib/store";
import { Toggle } from "@/components/ui/Toggle";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Orchestration options
// ---------------------------------------------------------------------------
// We store the orchestration choice in config.channel (not used for other
// purposes in wizard steps 1-4). The deploy step maps this back to the YAML
// orchestration.pattern field.
// ---------------------------------------------------------------------------

const ORCHESTRATION_OPTIONS = [
  {
    id: "single_pass",
    label: "Respond directly",
    description: "Single model call. Fast, low cost. Best for simple Q&A.",
    icon: "⚡",
  },
  {
    id: "react",
    label: "Think step by step",
    description: "ReAct pattern — reason and act iteratively with tools.",
    icon: "🧩",
  },
  {
    id: "plan_and_execute",
    label: "Plan before acting",
    description: "Generate a full plan, then execute each step in order.",
    icon: "🗺️",
  },
];

// Default channel value is "api" — treat that as single_pass not selected yet.
const DEFAULT_ORCH = "single_pass";

export function StepSettings() {
  const config = useWizardStore((s) => s.config);
  const updateConfig = useWizardStore((s) => s.updateConfig);

  // Map config.channel to orchestration selection.
  // "api" is the store default (not an orchestration ID), so fall back to
  // single_pass for display purposes.
  const orchValue =
    ORCHESTRATION_OPTIONS.find((o) => o.id === config.channel)?.id ??
    DEFAULT_ORCH;

  function setOrch(id: string) {
    updateConfig({ channel: id });
  }

  // Content filter is stored in memoryStrategy.
  const contentFilter = config.memoryStrategy === "content_filter";

  function toggleContentFilter(on: boolean) {
    updateConfig({
      memoryStrategy: on ? "content_filter" : "sliding_window",
    });
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-lg font-semibold text-am-text">Settings</h2>
        <p className="mt-1 text-sm text-am-text-dim">
          Configure memory, safety guardrails, and reasoning behaviour.
        </p>
      </div>

      {/* Memory */}
      <section className="rounded-xl border border-am-border bg-am-surface/60 p-5 space-y-4">
        <div className="flex items-center gap-2">
          <span className="text-base">🧠</span>
          <h3 className="text-sm font-semibold text-am-text">Memory</h3>
        </div>
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm text-am-text">Remember conversations</p>
            <p className="text-xs text-am-text-dim mt-0.5">
              Persist chat history across sessions for context continuity.
            </p>
          </div>
          <Toggle
            checked={config.memoryType === "conversational"}
            onChange={(v) =>
              updateConfig({ memoryType: v ? "conversational" : "none" })
            }
          />
        </div>
      </section>

      {/* Guardrails */}
      <section className="rounded-xl border border-am-border bg-am-surface/60 p-5 space-y-4">
        <div className="flex items-center gap-2">
          <span className="text-base">🛡️</span>
          <h3 className="text-sm font-semibold text-am-text">Guardrails</h3>
        </div>

        <div className="space-y-0 divide-y divide-am-border">
          <div className="flex items-center justify-between gap-4 pb-4">
            <div>
              <p className="text-sm text-am-text">
                Filter personal information (PII)
              </p>
              <p className="text-xs text-am-text-dim mt-0.5">
                Detect and redact names, emails, phone numbers, and IDs.
              </p>
            </div>
            <Toggle
              checked={config.guardrailsEnabled}
              onChange={(v) => updateConfig({ guardrailsEnabled: v })}
            />
          </div>

          <div className="flex items-center justify-between gap-4 pt-4">
            <div>
              <p className="text-sm text-am-text">
                Inappropriate content filter
              </p>
              <p className="text-xs text-am-text-dim mt-0.5">
                Block harmful, offensive, or out-of-policy outputs.
              </p>
            </div>
            <Toggle checked={contentFilter} onChange={toggleContentFilter} />
          </div>
        </div>
      </section>

      {/* Orchestration */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-base">⚙️</span>
          <h3 className="text-sm font-semibold text-am-text">Orchestration</h3>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {ORCHESTRATION_OPTIONS.map((opt) => {
            const selected = orchValue === opt.id;
            return (
              <button
                key={opt.id}
                onClick={() => setOrch(opt.id)}
                className={cn(
                  "flex flex-col gap-2 rounded-xl border p-4 text-left transition-all",
                  "hover:border-am-border-hover",
                  selected
                    ? "border-am-cyan shadow-[0_0_16px_rgba(0,212,255,0.2)] bg-am-cyan-dim"
                    : "border-am-border bg-am-surface"
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="text-lg leading-none">{opt.icon}</span>
                  <span
                    className={cn(
                      "text-sm font-semibold",
                      selected ? "text-am-cyan" : "text-am-text"
                    )}
                  >
                    {opt.label}
                  </span>
                  {selected && (
                    <span className="ml-auto h-2 w-2 rounded-full bg-am-cyan" />
                  )}
                </div>
                <p className="text-xs text-am-text-dim leading-snug">
                  {opt.description}
                </p>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
