import { describe, it, expect } from "vitest";
import { agentToNodes } from "../agent-to-nodes";
import { nodesToAgent } from "../nodes-to-agent";
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

describe("nodesToAgent", () => {
  it("round-trips pipeline nodes with agentToNodes", () => {
    const { nodes } = agentToNodes(SAMPLE);
    const snapshots = nodes.map((n) => ({
      id: n.id,
      data: n.data,
    }));
    const out = nodesToAgent(snapshots, SAMPLE);
    expect(out.spec.prompts.system).toBe(SAMPLE.spec.prompts.system);
    expect(out.spec.model.primary.provider).toBe("ollama");
    expect(out.spec.tools).toHaveLength(1);
    expect(out.spec.tools?.[0].name).toBe("search");
    expect(out.spec.guardrails?.input).toHaveLength(1);
    expect(out.spec.guardrails?.output).toHaveLength(1);
    expect(out.spec.memory?.conversational?.backend).toBe("redis");
  });

  it("updates system prompt from prompt node", () => {
    const { nodes } = agentToNodes(SAMPLE);
    const snapshots = nodes.map((n) => ({
      id: n.id,
      data:
        n.id === "prompt"
          ? { ...n.data, config: { system: "Updated." } }
          : n.data,
    }));
    const out = nodesToAgent(snapshots, SAMPLE);
    expect(out.spec.prompts.system).toBe("Updated.");
  });
});
