import type { ToolConfig } from "../types/agent";

/** Types whose wiring reads `description` (`_CLAVES_POR_TIPO`, runtime/engine.py). */
const READS_DESCRIPTION = new Set<string>(["agent", "client", "api"]);

export function readsDescription(type: string): boolean {
  return READS_DESCRIPTION.has(type);
}

const TYPES: { value: ToolConfig["type"]; label: string }[] = [
  { value: "builtin", label: "Built-in" },
  { value: "agent", label: "Sub-agent" },
  { value: "client", label: "Client (runs in the caller)" },
  { value: "integration", label: "Integration" },
  { value: "api", label: "API (manifest kept as-is)" },
  { value: "mcp", label: "MCP (manifest kept as-is)" },
];

/**
 * `api` and `mcp` need a manifest Forge cannot author; core raises on one without it and the
 * whole agent fails to bootstrap. Offer them only to a tool that already is that type.
 */
export function toolTypeOptions(current: string) {
  return TYPES.filter((t) => (t.value !== "api" && t.value !== "mcp") || t.value === current);
}

/** Apply panel edits over the original block; never emits keys core ignores for the type. */
export function applyToolEdit(
  orig: ToolConfig,
  edit: { name: string; type: ToolConfig["type"]; agent: string; description: string; max_result_tokens?: number },
): ToolConfig {
  const next: ToolConfig = { ...orig, name: edit.name, type: edit.type };
  if (edit.type === "agent") next.agent = edit.agent || edit.name;
  else delete next.agent;
  if (readsDescription(edit.type) && (edit.description || "description" in orig)) {
    next.description = edit.description;
  } else {
    delete next.description;
  }
  if (edit.max_result_tokens !== undefined) next.max_result_tokens = edit.max_result_tokens;
  else delete next.max_result_tokens;
  return next;
}
