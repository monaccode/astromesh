import type { AgentConfig } from "../types/agent";

type Knowledge = NonNullable<AgentConfig["spec"]["knowledge"]>;

/** Drop empty keys; top_k only with a pipeline; undefined when nothing is left. */
export function cleanKnowledge(k: Knowledge): Knowledge | undefined {
  const pipeline = k.pipeline?.trim();
  const bundle = k.bundle?.trim();
  const out: Knowledge = {};
  if (pipeline) out.pipeline = pipeline;
  if (pipeline && k.top_k && k.top_k >= 1) out.top_k = Math.floor(k.top_k);
  if (bundle) out.bundle = bundle;
  return pipeline || bundle ? out : undefined;
}
