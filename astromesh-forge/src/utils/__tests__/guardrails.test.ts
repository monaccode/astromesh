import { describe, expect, it } from "vitest";
import {
  GUARDRAIL_SPECS,
  defaultGuardrail,
  guardrailTypesFor,
  type GuardrailType,
} from "../guardrails";
import { PIPELINE_PRESETS } from "../../data/pipeline-presets";
import { agentToNodes } from "../agent-to-nodes";
import { nodesToAgent } from "../nodes-to-agent";
import type { AgentConfig } from "../../types/agent";

describe("guardrail specs", () => {
  it("offers each type only on the side core accepts", () => {
    expect(guardrailTypesFor("input")).toEqual([
      "pii_detection",
      "topic_filter",
      "max_length",
      "cost_limit",
    ]);
    expect(guardrailTypesFor("output")).toEqual(["pii_detection", "content_filter", "cost_limit"]);
  });

  it("defaults use the core default action", () => {
    expect(defaultGuardrail("pii_detection").action).toBe("redact");
    expect(defaultGuardrail("topic_filter").action).toBe("warn");
    expect(defaultGuardrail("max_length")).toMatchObject({ action: "truncate", max_chars: 10000 });
    expect(defaultGuardrail("content_filter").action).toBe("redact");
    expect(defaultGuardrail("cost_limit")).toEqual({
      type: "cost_limit",
      max_tokens_per_turn: 4000,
      count: "output",
    });
  });

  it("presets only produce valid rules for their side", () => {
    const guards = PIPELINE_PRESETS.filter((p) => p.build().category === "guardrail");
    expect(guards.length).toBeGreaterThan(0);
    for (const p of guards) {
      const n = p.build();
      const side = n.id.startsWith("ig-") ? "input" : "output";
      const cfg = n.config as {
        type: GuardrailType;
        action?: string;
        max_tokens_per_turn?: number;
      };
      expect(guardrailTypesFor(side)).toContain(cfg.type);
      if (cfg.action) expect(GUARDRAIL_SPECS[cfg.type].actions).toContain(cfg.action);
      if (cfg.type === "cost_limit") expect(cfg.max_tokens_per_turn).toBe(4000);
    }
  });

  it("round-trips type-specific fields through the canvas", () => {
    const cfg: AgentConfig = {
      apiVersion: "astromesh/v1",
      kind: "Agent",
      metadata: { name: "g" },
      spec: {
        identity: { display_name: "g", description: "g" },
        model: { primary: { provider: "ollama", model: "m" } },
        prompts: { system: "x" },
        orchestration: { pattern: "react" },
        guardrails: {
          input: [{ type: "topic_filter", action: "block", blocked_topics: ["a"], message: "no" }],
          output: [{ type: "cost_limit", max_tokens_per_turn: 4000, count: "total" }],
        },
      },
    } as AgentConfig;
    const { nodes } = agentToNodes(cfg);
    const out = nodesToAgent(nodes.map((n) => ({ id: n.id, data: n.data })), cfg);
    expect(out.spec.guardrails).toEqual(cfg.spec.guardrails);
  });
});
