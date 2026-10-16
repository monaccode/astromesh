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

/**
 * Every candidate the canvas shows as a node. Role shape: all of `default.candidates`, in
 * core's order (the router tries them in list order, reordered only by the strategy).
 * Legacy: `primary`, `fallback`.
 */
export function modelCandidates(m: ModelSpec): ModelConfig[] {
  if (isRoleShape(m)) return m.default?.candidates ?? [];
  return [m.primary, m.fallback].filter((c): c is ModelConfig => !!c);
}

/** Node id for candidate `i`: `model-primary`, `model-fallback`, then `model-<i>`. */
export function modelNodeId(i: number): string {
  return i === 0 ? "model-primary" : i === 1 ? "model-fallback" : `model-${i}`;
}

export function modelNodeIndex(id: string): number {
  if (id === "model-primary") return 0;
  if (id === "model-fallback") return 1;
  const n = /^model-(\d+)$/.exec(id);
  return n ? Number(n[1]) : Number.MAX_SAFE_INTEGER;
}

export function modelNodeLabel(id: string, c: ModelConfig | undefined): string {
  const i = modelNodeIndex(id);
  if (i === 0) return candidateLabel(c);
  if (i === 1) return `Fallback: ${candidateLabel(c)}`;
  return `Candidate ${i + 1}: ${candidateLabel(c)}`;
}

/**
 * Write the canvas model nodes back. Each node is one candidate, so removing a node removes
 * exactly that candidate and nothing is inferred from a missing node on later saves.
 * Removing every model node keeps the base models (an agent with no model cannot run).
 */
export function withModelNodes(
  m: ModelSpec,
  nodes: { id: string; config: ModelConfig }[],
): ModelSpec {
  if (!nodes.length) return m;
  const byId = (id: string) => nodes.find((n) => n.id === id)?.config;
  if (isRoleShape(m)) {
    const candidates = [...nodes]
      .sort((a, b) => modelNodeIndex(a.id) - modelNodeIndex(b.id))
      .map((n) => n.config);
    return { ...m, default: { ...m.default, candidates } };
  }
  const out: ModelSpec = { ...m, primary: byId("model-primary") ?? m.primary };
  const fallback = byId("model-fallback");
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
