import { describe, it, expect } from "vitest";
import { agentToNodes } from "../agent-to-nodes";
import { nodesToAgent } from "../nodes-to-agent";
import { agentToYaml, yamlToAgent } from "../yaml";
import { toRoleShape, withSource } from "../model";
import type { AgentConfig } from "../../types/agent";

// A manifest using sections Forge has no dedicated UI for (core 0.70.0). Nothing may be lost.
const RICH = `
apiVersion: astromesh/v1
kind: Agent
metadata: {name: rich, version: 1.0.0, namespace: demo}
spec:
  identity: {display_name: Rich, description: every section}
  model:
    default:
      candidates:
        - {source: ollama, model: "llama3.1:8b", endpoint: "http://localhost:11434", context_window: 8192, timeout: 30}
        - {providerRef: gateway-kimi, model: kimi-k2}
        - {source: litellm, model: "anthropic/claude", api_key_env: ANTHROPIC_API_KEY}
      strategy: capability_match
    roles:
      planner:
        candidates: [{source: centinela, endpoint_name: plan, contract: {schema: x}, max_retries: 2}]
        strategy: quality_first
  prompts:
    system: "You are rich."
    context: "Today: {{ prefetch.today }}"
    templates: {greet: "hi"}
  orchestration:
    pattern: pipeline
    max_iterations: 4
    stages: [draft, review]
    max_tool_result_tokens: 2000
    role_map: {plan: planner}
  program: null
  prefetch: [{tool: clock, as: today}]
  output_schema: {type: object, properties: {answer: {type: string}}}
  chain: {steps: [{agent: a}, {agent: b}]}
  tools:
    - {name: search, type: builtin, max_result_tokens: 500, rate_limit: {calls: 5, period: 60}}
    - {name: crm, type: integration, connection: hubspot, actions: [create_contact], confirm: [create_contact]}
    - {name: fs, type: mcp, server: {command: npx, args: [fs]}}
    - {name: weather, type: api, endpoint: "https://w", method: GET}
    - {name: sub, type: agent, agent: helper, context_transform: last}
    - {name: pick, type: client, parameters: {x: {type: string}}}
  knowledge: {pipeline: docs, top_k: 3}
  memory:
    conversational: {backend: redis, connection: {url: "redis://r:6379/0"}, strategy: summary, max_turns: 30}
    semantic: {backend: chromadb, similarity_threshold: 0.8}
    episodic: {backend: sqlite}
  guardrails:
    input:
      - {type: topic_filter, blocked_topics: [a]}
      - {type: topic_filter, blocked_topics: [b]}
    output:
      - {type: cost_limit, max_tokens_per_turn: 100}
  permissions: {allowed_actions: [read]}
  observability: {sample_rate: 1}
`;

function canvasRoundTrip(cfg: AgentConfig): AgentConfig {
  const { nodes } = agentToNodes(cfg);
  return nodesToAgent(nodes.map((n) => ({ id: n.id, data: n.data })), cfg);
}

describe("core 0.70 manifest round-trip", () => {
  it("canvas + YAML round-trip keeps every section unchanged", () => {
    const cfg = yamlToAgent(RICH);
    const out = yamlToAgent(agentToYaml(canvasRoundTrip(cfg)));
    expect(out).toEqual(cfg);
  });

  it("renders model.default/roles agents without crashing", () => {
    const cfg = yamlToAgent(RICH);
    const { nodes } = agentToNodes(cfg);
    expect(nodes.find((n) => n.id === "model-primary")?.data.label).toBe("ollama/llama3.1:8b");
    expect(nodes.find((n) => n.id === "model-fallback")?.data.label).toBe("Fallback: ref:gateway-kimi/kimi-k2");
  });

  it("gives same-type guardrails distinct node ids and keeps both", () => {
    const cfg = yamlToAgent(RICH);
    const ids = agentToNodes(cfg).nodes.map((n) => n.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(canvasRoundTrip(cfg).spec.guardrails?.input).toHaveLength(2);
  });

  it("shows every default candidate as a node and editing one keeps the rest", () => {
    const cfg = yamlToAgent(RICH);
    const { nodes } = agentToNodes(cfg);
    expect(nodes.filter((n) => n.data.category === "model").map((n) => n.id)).toEqual([
      "model-primary",
      "model-fallback",
      "model-2",
    ]);
    const snaps = nodes.map((n) => ({
      id: n.id,
      data: n.id === "model-primary" ? { ...n.data, config: { ...n.data.config, model: "qwen" } } : n.data,
    }));
    const m = nodesToAgent(snaps, cfg).spec.model;
    expect(m.default?.candidates.map((c) => c.model)).toEqual(["qwen", "kimi-k2", "anthropic/claude"]);
    expect(m.default?.candidates[0].context_window).toBe(8192);
    expect(m.roles).toEqual(cfg.spec.model.roles);
  });

  it("removing the fallback node removes exactly that candidate, stable across saves", () => {
    const cfg = yamlToAgent(RICH);
    const snaps = agentToNodes(cfg)
      .nodes.filter((n) => n.id !== "model-fallback")
      .map((n) => ({ id: n.id, data: n.data }));
    const once = nodesToAgent(snaps, cfg);
    const twice = nodesToAgent(snaps, once);
    const models = (c: AgentConfig) => c.spec.model.default?.candidates.map((x) => x.model);
    expect(models(once)).toEqual(["llama3.1:8b", "anthropic/claude"]);
    expect(models(twice)).toEqual(models(once));
  });

  it("converts legacy model to the default role", () => {
    const m = toRoleShape({
      primary: { provider: "ollama", model: "a" },
      fallback: { provider: "openai", model: "b" },
      routing: { strategy: "round_robin" },
    });
    expect(m).toEqual({
      default: {
        candidates: [
          { provider: "ollama", model: "a" },
          { provider: "openai", model: "b" },
        ],
        strategy: "round_robin",
      },
    });
  });

  it("withSource writes the key the candidate already uses, and clears on auto", () => {
    expect(withSource({ source: "ollama" }, "litellm")).toEqual({ source: "litellm" });
    expect(withSource({ provider: "ollama" }, "openai")).toEqual({ provider: "openai" });
    expect(withSource({ provider: "ollama", providerRef: "g" }, "")).toEqual({ providerRef: "g" });
  });
});

describe("memory defaults", () => {
  it("conversational default is a backend core builds, with connection.url", async () => {
    const { DEFAULT_CONVERSATIONAL, PIPELINE_PRESETS } = await import("../../data/pipeline-presets");
    expect(DEFAULT_CONVERSATIONAL.backend).toBe("redis");
    expect(DEFAULT_CONVERSATIONAL.connection?.url).toMatch(/^redis:\/\//);
    const mem = PIPELINE_PRESETS.filter((p) => p.section === "memory").map((p) => p.build().config);
    expect(mem.every((c) => c.backend === "redis" && (c.connection as { url?: string })?.url)).toBe(true);
  });
});

describe("applyToolEdit", () => {
  it("writes description only for types that read it, when non-empty or already present", async () => {
    const { applyToolEdit } = await import("../tools");
    const edit = { name: "t", agent: "", description: "", max_result_tokens: undefined };
    expect(applyToolEdit({ name: "t", type: "builtin", description: "x" }, { ...edit, type: "builtin" })).toEqual({ name: "t", type: "builtin" });
    expect(applyToolEdit({ name: "t", type: "client" }, { ...edit, type: "client" })).toEqual({ name: "t", type: "client" });
    expect(applyToolEdit({ name: "t", type: "client", description: "old" }, { ...edit, type: "client" })).toEqual({ name: "t", type: "client", description: "" });
    expect(applyToolEdit({ name: "t", type: "client" }, { ...edit, type: "client", description: "d" })).toEqual({ name: "t", type: "client", description: "d" });
  });
});
