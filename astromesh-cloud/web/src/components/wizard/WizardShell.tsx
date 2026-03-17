"use client";

import { useState } from "react";
import { useWizardStore } from "@/lib/store";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import { StepIdentity } from "./StepIdentity";
import { StepModel } from "./StepModel";
import { StepTools } from "./StepTools";
import { StepSettings } from "./StepSettings";
import { StepDeploy } from "./StepDeploy";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

const STEPS = [
  { id: 1, label: "Identity" },
  { id: 2, label: "Model" },
  { id: 3, label: "Tools" },
  { id: 4, label: "Settings" },
  { id: 5, label: "Deploy" },
] as const;

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

type Config = ReturnType<typeof useWizardStore.getState>["config"];

function validate(step: number, config: Config): string | null {
  if (step === 1) {
    if (!config.displayName.trim()) return "Display name is required.";
    if (!config.agentName.trim()) return "Agent slug is required.";
  }
  if (step === 2) {
    if (!config.model) return "Please select a model.";
  }
  return null;
}

// ---------------------------------------------------------------------------
// YAML preview builder
// ---------------------------------------------------------------------------

function buildYamlPreview(config: Config): string {
  const toolLines =
    config.tools.length > 0
      ? config.tools.map((t) => `    - id: ${t}`).join("\n")
      : "    []";

  const promptLines = config.systemPrompt
    ? config.systemPrompt
        .split("\n")
        .map((l, i) => (i === 0 ? l : `      ${l}`))
        .join("\n")
    : "# (empty)";

  return `apiVersion: astromesh/v1
kind: Agent
metadata:
  name: ${config.agentName || "<slug>"}
spec:
  identity:
    displayName: "${config.displayName || ""}"
    tone: ${config.tone}
  model:
    primary: ${config.model}
    routing: ${config.routingStrategy}
  orchestration:
    pattern: ${config.channel || "single_pass"}
  prompts:
    system: |
      ${promptLines}
  tools:
${toolLines}
  memory:
    type: ${config.memoryType}
  guardrails:
    enabled: ${config.guardrailsEnabled}`;
}

// ---------------------------------------------------------------------------
// Step renderer
// ---------------------------------------------------------------------------

function StepContent({ step }: { step: number }) {
  switch (step) {
    case 1:
      return <StepIdentity />;
    case 2:
      return <StepModel />;
    case 3:
      return <StepTools />;
    case 4:
      return <StepSettings />;
    case 5:
      return <StepDeploy />;
    default:
      return <StepIdentity />;
  }
}

// ---------------------------------------------------------------------------
// WizardShell
// ---------------------------------------------------------------------------

export function WizardShell() {
  const step = useWizardStore((s) => s.step);
  const setStep = useWizardStore((s) => s.setStep);
  const config = useWizardStore((s) => s.config);
  const [error, setError] = useState<string | null>(null);

  const isFirst = step === 1;
  const isLast = step === 5;
  const progress = ((step - 1) / (STEPS.length - 1)) * 100;
  const yaml = buildYamlPreview(config);

  function handleNext() {
    const err = validate(step, config);
    if (err) {
      setError(err);
      return;
    }
    setError(null);
    if (!isLast) setStep(step + 1);
  }

  function handlePrev() {
    setError(null);
    if (!isFirst) setStep(step - 1);
  }

  function handleStepClick(targetStep: number) {
    // Allow free backward navigation; block forward-jumping
    if (targetStep < step) {
      setError(null);
      setStep(targetStep);
    }
  }

  return (
    <div className="flex flex-col gap-0 min-h-[calc(100vh-10rem)]">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-am-text tracking-tight">
          New Agent
        </h1>
        <p className="mt-1 text-sm text-am-text-dim">
          Configure and deploy your AI agent in minutes.
        </p>
      </div>

      {/* Progress bar */}
      <div className="mb-8">
        <div className="relative mb-3">
          <div className="h-1 w-full rounded-full bg-am-border" />
          <div
            className="absolute top-0 left-0 h-1 rounded-full bg-am-cyan transition-all duration-500 shadow-[0_0_8px_rgba(0,212,255,0.5)]"
            style={{ width: `${progress}%` }}
          />
        </div>

        <div className="grid grid-cols-5 text-center">
          {STEPS.map((s) => (
            <button
              key={s.id}
              onClick={() => handleStepClick(s.id)}
              className={cn(
                "flex flex-col items-center gap-1 px-1 transition-colors",
                s.id === step
                  ? "text-am-cyan"
                  : s.id < step
                  ? "text-am-text-dim hover:text-am-text cursor-pointer"
                  : "text-am-text-dim/40 cursor-default"
              )}
            >
              <span
                className={cn(
                  "inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-semibold",
                  s.id === step
                    ? "bg-am-cyan text-am-bg"
                    : s.id < step
                    ? "bg-am-cyan/20 text-am-cyan border border-am-cyan/30"
                    : "bg-am-border/50 text-am-text-dim/50"
                )}
              >
                {s.id < step ? "✓" : s.id}
              </span>
              <span className="text-xs font-medium leading-tight">{s.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Main layout: step content + optional YAML side panel */}
      <div className="flex flex-1 items-start gap-6">
        {/* Step content column */}
        <div className="flex-1 min-w-0 flex flex-col">
          <div className="rounded-xl border border-am-border bg-am-surface p-6">
            <StepContent step={step} />
          </div>

          {/* Inline validation error */}
          {error && (
            <p className="mt-3 text-sm text-am-red">{error}</p>
          )}

          {/* Navigation buttons */}
          <div className="mt-6 flex items-center justify-between">
            <Button
              variant="secondary"
              onClick={handlePrev}
              disabled={isFirst}
            >
              ← Previous
            </Button>

            {/* Dot progress indicators */}
            <div className="flex items-center gap-1">
              {STEPS.map((s) => (
                <span
                  key={s.id}
                  className={cn(
                    "h-1.5 rounded-full transition-all duration-300",
                    s.id === step
                      ? "w-6 bg-am-cyan"
                      : s.id < step
                      ? "w-1.5 bg-am-cyan/50"
                      : "w-1.5 bg-am-border"
                  )}
                />
              ))}
            </div>

            <Button variant="primary" onClick={handleNext}>
              {isLast ? "Deploy →" : "Next →"}
            </Button>
          </div>
        </div>

        {/* YAML preview panel — visible at xl breakpoint and up */}
        <aside className="hidden xl:flex w-80 flex-shrink-0 sticky top-24 flex-col">
          <div className="rounded-xl border border-am-border bg-am-bg overflow-hidden">
            <div className="flex items-center justify-between border-b border-am-border px-4 py-2.5">
              <span className="text-xs font-medium text-am-text-dim uppercase tracking-wide">
                Live Preview
              </span>
              <span className="text-xs text-am-cyan font-mono">agent.yaml</span>
            </div>
            <pre className="p-4 text-xs font-mono text-am-text-dim leading-relaxed overflow-x-auto whitespace-pre-wrap break-words max-h-[70vh] overflow-y-auto">
              {yaml}
            </pre>
          </div>
        </aside>
      </div>
    </div>
  );
}
