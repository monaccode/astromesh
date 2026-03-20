import type { AgentConfig } from "../types/agent";
import type { ForgeEdge } from "../types/canvas";

interface PipelineNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: { label: string; category: string; config: Record<string, unknown> };
}

export function agentToNodes(config: AgentConfig): {
  nodes: PipelineNode[];
  edges: ForgeEdge[];
} {
  const nodes: PipelineNode[] = [];
  const edges: ForgeEdge[] = [];
  let y = 0;
  const x = 250;
  const step = 120;
  let prevId: string | null = null;

  function addNode(id: string, label: string, category: string, nodeConfig: Record<string, unknown> = {}) {
    nodes.push({ id, type: "pipeline", position: { x, y }, data: { label, category, config: nodeConfig } });
    if (prevId) edges.push({ id: `${prevId}-${id}`, source: prevId, target: id });
    prevId = id;
    y += step;
  }

  // Input guardrails
  const inputGuardrails = config.spec.guardrails?.input || [];
  for (const g of inputGuardrails) {
    addNode(`ig-${g.type}`, `Input: ${g.type}`, "guardrail", g as unknown as Record<string, unknown>);
  }

  // Memory
  if (config.spec.memory?.conversational) {
    addNode("memory-conv", "Conversational Memory", "memory", config.spec.memory.conversational as unknown as Record<string, unknown>);
  }
  if (config.spec.memory?.semantic) {
    addNode("memory-sem", "Semantic Memory", "memory", config.spec.memory.semantic as unknown as Record<string, unknown>);
  }

  // Prompt
  addNode("prompt", "System Prompt", "prompt", { system: config.spec.prompts.system });

  // Model
  addNode("model-primary", `${config.spec.model.primary.provider}/${config.spec.model.primary.model}`, "model", config.spec.model.primary as unknown as Record<string, unknown>);
  if (config.spec.model.fallback) {
    addNode("model-fallback", `Fallback: ${config.spec.model.fallback.provider}/${config.spec.model.fallback.model}`, "model", config.spec.model.fallback as unknown as Record<string, unknown>);
  }

  // Tools
  const tools = config.spec.tools || [];
  for (const t of tools) {
    addNode(`tool-${t.name}`, t.name, "tool", t as unknown as Record<string, unknown>);
  }

  // Output guardrails
  const outputGuardrails = config.spec.guardrails?.output || [];
  for (const g of outputGuardrails) {
    addNode(`og-${g.type}`, `Output: ${g.type}`, "guardrail", g as unknown as Record<string, unknown>);
  }

  return { nodes, edges };
}
