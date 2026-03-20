import { describe, it, expect } from "vitest";
import { agentToNodes } from "../agent-to-nodes";
import type { AgentConfig } from "../../types/agent";

const SAMPLE: AgentConfig = {
  apiVersion: "astromesh/v1",
  kind: "Agent",
  metadata: { name: "test", version: "1.0.0" },
  spec: {
    identity: { display_name: "Test Agent", description: "A test" },
    model: {
      primary: { provider: "ollama", model: "llama3.1:8b" },
      routing: { strategy: "cost_optimized" },
    },
    prompts: { system: "You are a test agent." },
    orchestration: { pattern: "react", max_iterations: 5 },
    tools: [{ name: "search", type: "internal", description: "Search" }],
    guardrails: {
      input: [{ type: "pii_detection", action: "redact" }],
      output: [{ type: "cost_limit" }],
    },
    memory: {
      conversational: { backend: "redis", strategy: "sliding_window", max_turns: 20 },
    },
  },
};

describe("agentToNodes", () => {
  it("creates nodes for all pipeline components", () => {
    const { nodes, edges } = agentToNodes(SAMPLE);
    const categories = nodes.map((n) => n.data.category);
    expect(categories).toContain("guardrail");
    expect(categories).toContain("memory");
    expect(categories).toContain("prompt");
    expect(categories).toContain("model");
    expect(categories).toContain("tool");
    expect(edges.length).toBeGreaterThan(0);
  });

  it("creates correct number of nodes", () => {
    const { nodes } = agentToNodes(SAMPLE);
    // 1 input guardrail + 1 memory + 1 prompt + 1 model + 1 tool + 1 output guardrail = 6
    expect(nodes).toHaveLength(6);
  });
});
