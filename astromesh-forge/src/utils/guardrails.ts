import type { GuardrailConfig } from "../types/agent";

export type GuardrailSide = "input" | "output";

/** Mirrors `_RULES` in astromesh/core/guardrails.py (core 0.70.0). First action is the default. */
export const GUARDRAIL_SPECS = {
  pii_detection: { label: "PII Detection", sides: ["input", "output"], actions: ["redact", "block", "warn"] },
  topic_filter: { label: "Topic Filter", sides: ["input"], actions: ["warn", "block"] },
  max_length: { label: "Max Length", sides: ["input"], actions: ["truncate", "block"] },
  content_filter: { label: "Content Filter", sides: ["output"], actions: ["redact", "block"] },
  cost_limit: { label: "Cost Limit", sides: ["input", "output"], actions: ["block"] },
} as const satisfies Record<
  string,
  { label: string; sides: readonly GuardrailSide[]; actions: readonly string[] }
>;

export type GuardrailType = keyof typeof GUARDRAIL_SPECS;

export const COST_LIMIT_DEFAULT_TOKENS = 4000;
export const MAX_LENGTH_DEFAULT_CHARS = 10000;

export function guardrailTypesFor(side: GuardrailSide): GuardrailType[] {
  return (Object.keys(GUARDRAIL_SPECS) as GuardrailType[]).filter((t) =>
    (GUARDRAIL_SPECS[t].sides as readonly string[]).includes(side),
  );
}

export function isGuardrailType(t: string): t is GuardrailType {
  return t in GUARDRAIL_SPECS;
}

/** A valid rule for `type`, with the core default action and required fields filled in. */
export function defaultGuardrail(type: GuardrailType): GuardrailConfig {
  const action = GUARDRAIL_SPECS[type].actions[0];
  switch (type) {
    case "topic_filter":
      return { type, action, blocked_topics: [] };
    case "max_length":
      return { type, action, max_chars: MAX_LENGTH_DEFAULT_CHARS };
    case "content_filter":
      return { type, action, blocked_patterns: [], forbidden_keywords: [] };
    case "cost_limit":
      return { type, max_tokens_per_turn: COST_LIMIT_DEFAULT_TOKENS, count: "output" };
    default:
      return { type, action };
  }
}
