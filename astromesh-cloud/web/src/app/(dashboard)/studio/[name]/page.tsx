"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAuthStore, useWizardStore } from "@/lib/store";
import { WizardShell } from "@/components/wizard/WizardShell";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Map an agent config object returned by the API into the flat WizardConfig
 * shape. The API may return a full agent YAML spec or a flat config; we handle
 * both patterns gracefully via optional chaining.
 */
function mapApiConfigToWizard(
  data: Record<string, unknown>
): Partial<import("@/lib/store").WizardConfig> {
  // Support both top-level keys (flat) and nested spec (YAML-shaped)
  const spec = (data.spec as Record<string, unknown> | undefined) ?? data;

  const identity = (spec.identity as Record<string, unknown> | undefined) ?? {};
  const modelSpec = (spec.model as Record<string, unknown> | undefined) ?? {};
  const promptsSpec = (spec.prompts as Record<string, unknown> | undefined) ?? {};
  const toolsSpec = spec.tools;
  const memorySpec = (spec.memory as Record<string, unknown> | undefined) ?? {};
  const orchSpec = (spec.orchestration as Record<string, unknown> | undefined) ?? {};
  const guardrailsSpec =
    (spec.guardrails as Record<string, unknown> | undefined) ?? {};

  const agentName =
    (data.name as string | undefined) ??
    ((data.metadata as Record<string, unknown> | undefined)?.name as
      | string
      | undefined) ??
    "";

  const tools = Array.isArray(toolsSpec)
    ? toolsSpec.map((t: unknown) => {
        if (typeof t === "string") return t;
        if (typeof t === "object" && t !== null) {
          const obj = t as Record<string, unknown>;
          return (obj.id as string | undefined) ?? "";
        }
        return "";
      }).filter(Boolean)
    : [];

  return {
    agentName,
    displayName: (identity.displayName as string | undefined) ?? (data.displayName as string | undefined) ?? agentName,
    description: (identity.description as string | undefined) ?? (data.description as string | undefined) ?? "",
    provider: (modelSpec.provider as string | undefined) ?? (data.provider as string | undefined) ?? "openai",
    model: (modelSpec.primary as string | undefined) ?? (data.model as string | undefined) ?? "gpt-4o-mini",
    routingStrategy: (modelSpec.routing as string | undefined) ?? (data.routingStrategy as string | undefined) ?? "cost_optimized",
    fallbackModel: (modelSpec.fallback as string | undefined) ?? (data.fallbackModel as string | undefined) ?? "",
    systemPrompt: (promptsSpec.system as string | undefined) ?? (data.systemPrompt as string | undefined) ?? "",
    tone: (identity.tone as string | undefined) ?? (data.tone as string | undefined) ?? "professional",
    tools,
    memoryType: (memorySpec.type as string | undefined) ?? (data.memoryType as string | undefined) ?? "conversational",
    memoryStrategy: (memorySpec.strategy as string | undefined) ?? (data.memoryStrategy as string | undefined) ?? "sliding_window",
    channel: (orchSpec.pattern as string | undefined) ?? (data.channel as string | undefined) ?? "api",
    guardrailsEnabled:
      (guardrailsSpec.enabled as boolean | undefined) ??
      (data.guardrailsEnabled as boolean | undefined) ??
      true,
    maxIterations:
      ((orchSpec.maxIterations as number | undefined) ??
        (data.maxIterations as number | undefined) ??
        10),
  };
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function EditAgentPage() {
  const params = useParams<{ name: string }>();
  const agentName = params.name;

  const orgSlug = useAuthStore((s) => s.orgSlug);
  const resetWizard = useWizardStore((s) => s.resetWizard);
  const updateConfig = useWizardStore((s) => s.updateConfig);
  const setStep = useWizardStore((s) => s.setStep);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!orgSlug || !agentName) return;

    // Reset wizard to defaults before loading so stale state doesn't bleed in
    resetWizard();

    let cancelled = false;

    async function loadAgent() {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getAgent(orgSlug!, agentName);
        if (cancelled) return;
        const mapped = mapApiConfigToWizard(data as Record<string, unknown>);
        updateConfig(mapped);
        // Start on step 1 so the user can review from the beginning
        setStep(1);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load agent.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadAgent();

    return () => {
      cancelled = true;
    };
  }, [orgSlug, agentName, resetWizard, updateConfig, setStep]);

  if (loading) {
    return (
      <div className="flex flex-col gap-4 min-h-[40vh] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-am-cyan border-t-transparent" />
        <p className="text-sm text-am-text-dim">Loading agent configuration…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-am-red/20 bg-am-red/5 px-6 py-8 text-center">
        <p className="text-sm font-medium text-am-red mb-1">Failed to load agent</p>
        <p className="text-xs text-am-text-dim">{error}</p>
      </div>
    );
  }

  return <WizardShell isEdit />;
}
