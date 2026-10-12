import type { AgentConfig } from "../types/agent";

type Knowledge = NonNullable<AgentConfig["spec"]["knowledge"]>;

/**
 * Drop empty keys; top_k only with a pipeline; undefined when nothing is left.
 * `commit: false` keeps raw values (so spaces can be typed); `true` trims them.
 */
export function cleanKnowledge(k: Knowledge, commit = true): Knowledge | undefined {
  const norm = (v?: string) => (commit ? v?.trim() : v);
  const pipeline = norm(k.pipeline);
  const bundle = norm(k.bundle);
  const out: Knowledge = {};
  if (pipeline?.trim()) out.pipeline = pipeline;
  if (pipeline?.trim() && k.top_k && k.top_k >= 1) out.top_k = Math.floor(k.top_k);
  if (bundle?.trim()) out.bundle = bundle;
  return out.pipeline || out.bundle ? out : undefined;
}
