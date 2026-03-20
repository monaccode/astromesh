import type { AgentConfig, ToolConfig, GuardrailConfig, MemoryConfig } from "../types/agent";

interface PipelineNode {
  id: string;
  data: { label: string; category: string; config: Record<string, unknown> };
}

export function nodesToAgent(
  nodes: PipelineNode[],
  baseConfig: AgentConfig
): AgentConfig {
  const config = structuredClone(baseConfig);

  const tools: ToolConfig[] = nodes
    .filter((n) => n.data.category === "tool")
    .map((n) => n.data.config as unknown as ToolConfig);
  if (tools.length) config.spec.tools = tools;

  const inputGuardrails: GuardrailConfig[] = nodes
    .filter((n) => n.data.category === "guardrail" && n.id.startsWith("ig-"))
    .map((n) => n.data.config as GuardrailConfig);
  const outputGuardrails: GuardrailConfig[] = nodes
    .filter((n) => n.data.category === "guardrail" && n.id.startsWith("og-"))
    .map((n) => n.data.config as GuardrailConfig);
  if (inputGuardrails.length || outputGuardrails.length) {
    config.spec.guardrails = {
      input: inputGuardrails.length ? inputGuardrails : undefined,
      output: outputGuardrails.length ? outputGuardrails : undefined,
    };
  }

  const memoryNodes = nodes.filter((n) => n.data.category === "memory");
  if (memoryNodes.length) {
    config.spec.memory = {};
    for (const mn of memoryNodes) {
      if (mn.id.includes("conv")) config.spec.memory.conversational = mn.data.config as unknown as MemoryConfig;
      if (mn.id.includes("sem")) config.spec.memory.semantic = mn.data.config as unknown as MemoryConfig;
      if (mn.id.includes("epi")) config.spec.memory.episodic = mn.data.config as unknown as MemoryConfig;
    }
  }

  return config;
}
