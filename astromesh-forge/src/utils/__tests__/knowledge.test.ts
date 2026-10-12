import { describe, it, expect } from "vitest";
import { cleanKnowledge } from "../knowledge";
import { agentToYaml, yamlToAgent } from "../yaml";
import { agentToNodes } from "../agent-to-nodes";
import { nodesToAgent } from "../nodes-to-agent";

describe("cleanKnowledge", () => {
  it("drops empty keys and the whole block", () => {
    expect(cleanKnowledge({ pipeline: "", bundle: " ", top_k: 3 })).toBeUndefined();
    expect(cleanKnowledge({})).toBeUndefined();
  });
  it("keeps bundle alone and drops top_k without pipeline", () => {
    expect(cleanKnowledge({ bundle: "kb/okf", top_k: 4 })).toEqual({ bundle: "kb/okf" });
  });
  it("keeps top_k with pipeline", () => {
    expect(cleanKnowledge({ pipeline: "docs", top_k: 4 })).toEqual({ pipeline: "docs", top_k: 4 });
  });
  it("drops invalid top_k", () => {
    expect(cleanKnowledge({ pipeline: "docs", top_k: 0 })).toEqual({ pipeline: "docs" });
  });
});

const YAML = `apiVersion: astromesh/v1
kind: Agent
metadata:
  name: kb-agent
  version: 1.0.0
spec:
  identity: {display_name: KB, description: d}
  model: {primary: {provider: ollama, model: llama3.1:8b}}
  prompts: {system: hi}
  orchestration: {pattern: react, max_iterations: 5}
  knowledge:
    bundle: knowledge/okf
`;

describe("spec.knowledge round-trip", () => {
  it("survives yaml and nodes", () => {
    const cfg = yamlToAgent(YAML);
    expect(cfg.spec.knowledge?.bundle).toBe("knowledge/okf");
    const back = nodesToAgent(
      agentToNodes(cfg).nodes.map((n) => ({ id: n.id, data: n.data })),
      cfg,
    );
    expect(yamlToAgent(agentToYaml(back)).spec.knowledge).toEqual({ bundle: "knowledge/okf" });
  });
});
