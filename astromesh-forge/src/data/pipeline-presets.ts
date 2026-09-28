import type { GuardrailConfig, MemoryConfig } from "../types/agent";

export type PresetSection = "builtin" | "memory" | "safety";

export interface PipelinePreset {
  id: string;
  section: PresetSection;
  title: string;
  hint: string;
  /** Used to avoid duplicate structural blocks */
  conflictKey?: string;
  build: () => {
    id: string;
    category: "tool" | "memory" | "guardrail";
    label: string;
    config: Record<string, unknown>;
  };
}

function memoryPreset(
  id: string,
  title: string,
  hint: string,
  slot: "conv" | "sem" | "epi",
  cfg: MemoryConfig,
): PipelinePreset {
  const suffix = slot === "conv" ? "memory-conv" : slot === "sem" ? "memory-sem" : "memory-epi";
  return {
    id,
    section: "memory",
    title,
    hint,
    conflictKey: suffix,
    build: () => ({
      id: `${suffix}-${Date.now()}`,
      category: "memory",
      label:
        slot === "conv"
          ? "Conversational memory"
          : slot === "sem"
            ? "Vector knowledge base"
            : "Event / audit log",
      config: { ...cfg } as unknown as Record<string, unknown>,
    }),
  };
}

function guardPreset(
  id: string,
  phase: "input" | "output",
  title: string,
  hint: string,
  cfg: GuardrailConfig,
): PipelinePreset {
  const prefix = phase === "input" ? "ig" : "og";
  return {
    id,
    section: "safety",
    title,
    hint,
    build: () => ({
      id: `${prefix}-${cfg.type}-${Date.now()}`,
      category: "guardrail",
      label: phase === "input" ? `Input: ${cfg.type}` : `Output: ${cfg.type}`,
      config: { ...cfg } as unknown as Record<string, unknown>,
    }),
  };
}

/** Curated blocks — user can refine fields in the properties panel. */
export const PIPELINE_PRESETS: PipelinePreset[] = [
  memoryPreset(
    "mem-chat",
    "Chat memory",
    "Short-term conversation context (e.g. Redis)",
    "conv",
    { backend: "redis", strategy: "sliding_window", max_turns: 20 },
  ),
  memoryPreset(
    "mem-vec",
    "Vector store",
    "Embeddings + similarity search (e.g. Chroma)",
    "sem",
    {
      backend: "chromadb",
      strategy: "similarity",
      max_results: 8,
      similarity_threshold: 0.72,
    },
  ),
  memoryPreset(
    "mem-epi",
    "Event log",
    "Append-only history for auditing",
    "epi",
    { backend: "sqlite", strategy: "append_only", ttl: 86400 },
  ),
  guardPreset("safe-pii", "input", "PII redaction", "Mask emails, phones, etc.", {
    type: "pii_detection",
    action: "redact",
  }),
  guardPreset("safe-toxic-in", "input", "Toxic input filter", "Block unsafe user content", {
    type: "content_filter",
    action: "block",
  }),
  guardPreset("safe-cost", "output", "Output cost guard", "Stop runaway token usage", {
    type: "cost_limit",
    action: "block",
  }),
];

export function presetsForSection(section: PresetSection): PipelinePreset[] {
  return PIPELINE_PRESETS.filter((p) => p.section === section);
}
