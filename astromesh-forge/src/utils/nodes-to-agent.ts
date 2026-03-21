import type {
  AgentConfig,
  GuardrailConfig,
  MemoryConfig,
  ModelConfig,
  ToolConfig,
} from "../types/agent";

export interface PipelineNodeSnapshot {
  id: string;
  data: {
    label: string;
    category: string;
    config: Record<string, unknown>;
  };
}

function asModelConfig(raw: Record<string, unknown>): ModelConfig {
  const parameters = raw.parameters as ModelConfig["parameters"] | undefined;
  return {
    provider: String(raw.provider ?? "ollama"),
    model: String(raw.model ?? ""),
    endpoint: raw.endpoint != null ? String(raw.endpoint) : undefined,
    api_key_env: raw.api_key_env != null ? String(raw.api_key_env) : undefined,
    parameters: parameters ?? {},
  };
}

export function nodesToAgent(
  nodes: PipelineNodeSnapshot[],
  baseConfig: AgentConfig,
): AgentConfig {
  const config = structuredClone(baseConfig);

  const promptNode = nodes.find((n) => n.data.category === "prompt");
  if (promptNode) {
    const system = promptNode.data.config.system;
    config.spec.prompts = {
      ...config.spec.prompts,
      system: typeof system === "string" ? system : String(system ?? ""),
    };
  }

  const primary = nodes.find((n) => n.id === "model-primary");
  if (primary) {
    config.spec.model.primary = asModelConfig(primary.data.config);
  }

  const fallback = nodes.find((n) => n.id === "model-fallback");
  if (fallback) {
    config.spec.model.fallback = asModelConfig(fallback.data.config);
  } else {
    delete config.spec.model.fallback;
  }

  const tools = nodes
    .filter((n) => n.data.category === "tool")
    .map((n) => n.data.config as unknown as ToolConfig);
  if (tools.length) {
    config.spec.tools = tools;
  } else {
    delete config.spec.tools;
  }

  const inputG = nodes
    .filter((n) => n.data.category === "guardrail" && n.id.startsWith("ig-"))
    .map((n) => n.data.config as GuardrailConfig);
  const outputG = nodes
    .filter((n) => n.data.category === "guardrail" && n.id.startsWith("og-"))
    .map((n) => n.data.config as GuardrailConfig);

  if (inputG.length || outputG.length) {
    config.spec.guardrails = {};
    if (inputG.length) {
      config.spec.guardrails.input = inputG;
    }
    if (outputG.length) {
      config.spec.guardrails.output = outputG;
    }
  } else {
    delete config.spec.guardrails;
  }

  const memNodes = nodes.filter((n) => n.data.category === "memory");
  if (memNodes.length) {
    const memory: NonNullable<AgentConfig["spec"]["memory"]> = {};
    for (const mn of memNodes) {
      const c = mn.data.config as unknown as MemoryConfig;
      if (mn.id.includes("conv")) {
        memory.conversational = c;
      } else if (mn.id.includes("sem")) {
        memory.semantic = c;
      } else if (mn.id.includes("epi")) {
        memory.episodic = c;
      }
    }
    if (Object.keys(memory).length) {
      config.spec.memory = memory;
    } else {
      delete config.spec.memory;
    }
  } else {
    delete config.spec.memory;
  }

  return config;
}
