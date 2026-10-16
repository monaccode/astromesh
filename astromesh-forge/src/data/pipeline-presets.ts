import type { GuardrailConfig, MemoryConfig } from "../types/agent";
import { defaultGuardrail } from "../utils/guardrails";

/**
 * Core only builds `redis` conversational memory (memory/factory.py) and needs
 * `connection.url`; semantic/episodic are ignored, so no presets offer them.
 */
export const DEFAULT_CONVERSATIONAL: MemoryConfig = {
  backend: "redis",
  connection: { url: "redis://redis:6379/0" },
  strategy: "sliding_window",
  max_turns: 20,
};

/** Backend dropdown: `redis` only; an unknown current value stays visible instead of being rewritten. */
export function memoryBackendOptions(current: string) {
  const opts = [{ value: "redis", label: "Redis" }];
  if (current && current !== "redis") opts.push({ value: current, label: `${current} (not built by core)` });
  return opts;
}

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
    DEFAULT_CONVERSATIONAL,
  ),
  guardPreset("safe-pii", "input", "PII redaction", "Mask emails, phones, etc.", defaultGuardrail("pii_detection")),
  guardPreset("safe-topics", "input", "Topic filter", "Warn on blocked topics (edit the list)", {
    ...defaultGuardrail("topic_filter"),
    blocked_topics: ["politics"],
  }),
  guardPreset("safe-length", "input", "Input length cap", "Truncate input to 10000 characters", defaultGuardrail("max_length")),
  guardPreset("safe-toxic-out", "output", "Output content filter", "Redact forbidden keywords/patterns", {
    ...defaultGuardrail("content_filter"),
    forbidden_keywords: ["password"],
  }),
  guardPreset("safe-cost", "output", "Output cost guard", "Stop runaway token usage (4000 output tokens per run)", defaultGuardrail("cost_limit")),
];

export function presetsForSection(section: PresetSection): PipelinePreset[] {
  return PIPELINE_PRESETS.filter((p) => p.section === section);
}
