import type { AgentConfig, ModelConfig } from "../types/agent";

type ModelSpec = AgentConfig["spec"]["model"];

/** Sources `build_candidate_provider` (runtime/engine.py) builds; anything else is dropped by core. */
export const PROVIDERS = [
  { value: "ollama", label: "Ollama" },
  { value: "openai_compat", label: "OpenAI compatible" },
  { value: "openai", label: "OpenAI" },
  { value: "azure_openai", label: "Azure OpenAI" },
  { value: "litellm", label: "LiteLLM" },
  { value: "centinela", label: "Centinela" },
];

/** `RoutingStrategy` in providers/base.py. */
export const ROUTING_STRATEGIES = [
  { value: "cost_optimized", label: "Cost Optimized" },
  { value: "latency_optimized", label: "Latency Optimized" },
  { value: "quality_first", label: "Quality First" },
  { value: "round_robin", label: "Round Robin" },
  { value: "capability_match", label: "Capability Match" },
];

/** True when the agent uses the per-role `default` + `roles` shape. */
export function isRoleShape(m: ModelSpec): boolean {
  return m.default != null || m.roles != null;
}

export function candidateSource(c: ModelConfig | undefined): string {
  return c?.source ?? c?.provider ?? "";
}

/** Set the adapter on whichever key the candidate already uses (`source` wins). */
export function withSource(c: ModelConfig, value: string): ModelConfig {
  const key = "source" in c ? "source" : "provider";
  const out = { ...c, [key]: value };
  if (!value) delete out[key];
  return out;
}

export function candidateLabel(c: ModelConfig | undefined): string {
  if (!c) return "(no model)";
  if (c.providerRef) return `ref:${c.providerRef}${c.model ? `/${c.model}` : ""}`;
  return `${candidateSource(c) || "auto"}/${c.model ?? ""}`;
}

/** The two candidates the canvas and the simple wizard edit, in either shape. */
export function modelSlots(m: ModelSpec): { primary?: ModelConfig; fallback?: ModelConfig } {
  if (isRoleShape(m)) {
    const c = m.default?.candidates ?? [];
    return { primary: c[0], fallback: c[1] };
  }
  return { primary: m.primary, fallback: m.fallback };
}

/** Write the two slots back without touching other candidates, roles or keys. */
export function withModelSlots(
  m: ModelSpec,
  primary: ModelConfig | undefined,
  fallback: ModelConfig | undefined,
): ModelSpec {
  if (isRoleShape(m)) {
    const rest = (m.default?.candidates ?? []).slice(2);
    const candidates = [primary, fallback, ...rest].filter((c): c is ModelConfig => !!c);
    return { ...m, default: { ...m.default, candidates } };
  }
  const out: ModelSpec = { ...m, primary };
  if (fallback) out.fallback = fallback;
  else delete out.fallback;
  return out;
}

/** Dropdown options; keeps an unknown current value visible instead of silently rewriting it. */
export function providerOptions(current: string) {
  const opts = [{ value: "", label: "Auto (infer, or from providerRef)" }, ...PROVIDERS];
  if (current && !PROVIDERS.some((p) => p.value === current)) {
    opts.push({ value: current, label: `${current} (not built by core)` });
  }
  return opts;
}

/** Legacy primary/fallback/routing → `default` role. Unrelated keys are kept. */
export function toRoleShape(m: ModelSpec): ModelSpec {
  if (isRoleShape(m)) return m;
  const { primary, fallback, routing, ...rest } = m;
  const candidates = [primary, fallback].filter((c): c is ModelConfig => !!c);
  return { ...rest, default: { candidates, strategy: routing?.strategy ?? "cost_optimized" } };
}
