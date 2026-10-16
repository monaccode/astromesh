import type {
  AgentConfig,
  GuardrailConfig,
  MemoryConfig,
  ModelConfig,
  ToolConfig,
} from "../types/agent";
import { withModelNodes } from "./model";

export interface PipelineNodeSnapshot {
  id: string;
  data: {
    label: string;
    category: string;
    config: Record<string, unknown>;
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

  // Node configs are the candidate blocks verbatim, so keys the canvas does not edit
  // (context_window, timeout, api_key_env, ...) survive. Works for both model shapes.
  config.spec.model = withModelNodes(
    config.spec.model,
    nodes
      .filter((n) => n.data.category === "model")
      .map((n) => ({ id: n.id, config: n.data.config as ModelConfig })),
  );

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
    // Start from the base so memory keys the canvas has no node for are kept.
    const memory: NonNullable<AgentConfig["spec"]["memory"]> = { ...config.spec.memory };
    delete memory.conversational;
    delete memory.semantic;
    delete memory.episodic;
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
