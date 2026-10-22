import { describe, it, expect } from "vitest";
import { a2aFormFrom, applyA2AForm, validateA2A, type A2AForm } from "../a2a";
import { applyToolEdit } from "../tools";
import { agentToNodes } from "../agent-to-nodes";
import { nodesToAgent } from "../nodes-to-agent";
import { agentToYaml, yamlToAgent } from "../yaml";
import type { ToolConfig } from "../../types/agent";

const BLANK: A2AForm = a2aFormFrom({ name: "x", type: "a2a" });
const OK: A2AForm = { ...BLANK, card_url: "https://agents.example.com/.well-known/agent-card.json" };

describe("validateA2A mirrors core (integrations/a2a.py)", () => {
  it("accepts a minimal https tool", () => {
    expect(validateA2A("remote", OK)).toEqual({});
  });

  it("requires name and card_url", () => {
    expect(validateA2A(" ", BLANK)).toEqual({ name: expect.any(String), card_url: expect.any(String) });
  });

  it("card_url: https only, http with allow_insecure_http; host; no credentials or spaces", () => {
    const err = (card_url: string, allow_insecure_http = false) =>
      validateA2A("r", { ...OK, card_url, allow_insecure_http }).card_url;
    expect(err("http://localhost:9000/card.json")).toBeDefined();
    expect(err("http://localhost:9000/card.json", true)).toBeUndefined();
    expect(err("HTTPS://Agents.example.com/c")).toBeUndefined();
    expect(err("ftp://x.example/c", true)).toBeDefined();
    expect(err("https:///card.json")).toBeDefined();
    expect(err("agents.example.com/card.json")).toBeDefined();
    expect(err("https://user:pw@x.example/c")).toBeDefined();
    expect(err("https://x.example/a b")).toBeDefined();
    expect(err("https://[::1]:8443/c")).toBeUndefined();
  });

  it("auth: an environment variable name, never a value", () => {
    const err = (authEnv: string) => validateA2A("r", { ...OK, authKind: "bearer_env", authEnv }).authEnv;
    expect(err("REMOTE_TOKEN")).toBeUndefined();
    expect(err("_x1")).toBeUndefined();
    expect(err("")).toBeDefined();
    expect(err("1TOKEN")).toBeDefined();
    expect(err("sk-live-abc123")).toBeDefined();
    expect(validateA2A("r", { ...OK, authKind: "none", authEnv: "sk-live" }).authEnv).toBeUndefined();
  });

  it("policy limits: max_bytes integer 1..16 MiB, timeout (0, 600]", () => {
    const e = (p: Partial<A2AForm>) => validateA2A("r", { ...OK, ...p });
    expect(e({ max_bytes: "16777216", timeout: "600" })).toEqual({});
    expect(e({ max_bytes: "16777217" }).max_bytes).toBeDefined();
    expect(e({ max_bytes: "0" }).max_bytes).toBeDefined();
    expect(e({ max_bytes: "1.5" }).max_bytes).toBeDefined();
    expect(e({ timeout: "0.5" }).timeout).toBeUndefined();
    expect(e({ timeout: "0" }).timeout).toBeDefined();
    expect(e({ timeout: "600.1" }).timeout).toBeDefined();
    expect(e({ timeout: "abc" }).timeout).toBeDefined();
  });
});

describe("applyA2AForm writes the YAML keys core reads", () => {
  it("full form → card_url, auth.{api_key_env|bearer_env}, policy.*", () => {
    const out = applyA2AForm(
      { name: "remote", type: "a2a" },
      {
        card_url: "http://localhost:9000/card.json",
        authKind: "api_key_env",
        authEnv: "AGENDA_KEY",
        max_bytes: "262144",
        timeout: "30",
        accept_parts: ["text", "data"],
        allow_insecure_http: true,
      },
    );
    expect(out).toEqual({
      name: "remote",
      type: "a2a",
      card_url: "http://localhost:9000/card.json",
      auth: { api_key_env: "AGENDA_KEY" },
      policy: { max_bytes: 262144, timeout: 30, accept_parts: ["text", "data"], allow_insecure_http: true },
    });
  });

  it("empty optional fields write no keys", () => {
    expect(applyA2AForm({ name: "r", type: "a2a" }, OK)).toEqual({ name: "r", type: "a2a", card_url: OK.card_url });
  });

  it("an existing a2a tool round-trips through the form unchanged", () => {
    const tool: ToolConfig = {
      name: "ag",
      type: "a2a",
      card_url: "https://x.example/card.json",
      auth: { bearer_env: "TOK" },
      policy: { timeout: 30, accept_parts: ["file"], allow_insecure_http: false },
      description: "d",
      rate_limit: { calls: 5, period: 60 },
    };
    expect(applyA2AForm(tool, a2aFormFrom(tool))).toEqual(tool);
  });
});

describe("newly created a2a tool round-trips canvas + YAML", () => {
  it("builtin tool switched to a2a in the panel survives save and reload", () => {
    const yaml = `
apiVersion: astromesh/v1
kind: Agent
metadata: {name: a, version: 1.0.0}
spec:
  identity: {display_name: A, description: d}
  model: {primary: {provider: ollama, model: m}}
  prompts: {system: s}
  orchestration: {pattern: react, max_iterations: 3}
  tools:
    - {name: search, type: builtin}
`;
    const cfg = yamlToAgent(yaml);
    const form: A2AForm = { ...OK, authKind: "bearer_env", authEnv: "REMOTE_TOKEN", timeout: "45" };
    expect(validateA2A("remote", form)).toEqual({});
    const edited = applyA2AForm(
      applyToolEdit(cfg.spec.tools![0], {
        name: "remote",
        type: "a2a",
        agent: "",
        description: "",
        max_result_tokens: undefined,
      }),
      form,
    );
    const { nodes } = agentToNodes(cfg);
    const snaps = nodes.map((n) => ({
      id: n.id,
      data: n.data.category === "tool" ? { ...n.data, config: { ...edited } } : n.data,
    }));
    const saved = yamlToAgent(agentToYaml(nodesToAgent(snaps, cfg)));
    const expected = {
      name: "remote",
      type: "a2a",
      card_url: OK.card_url,
      auth: { bearer_env: "REMOTE_TOKEN" },
      policy: { timeout: 45 },
    };
    expect(saved.spec.tools).toEqual([expected]);
    // And once more: reload → canvas → YAML changes nothing.
    const { nodes: n2 } = agentToNodes(saved);
    const again = yamlToAgent(agentToYaml(nodesToAgent(n2.map((n) => ({ id: n.id, data: n.data })), saved)));
    expect(again).toEqual(saved);
  });
});

describe("validateA2A edge cases the runtime rejects", () => {
  const err = (card_url: string) => validateA2A("r", { ...OK, card_url }).card_url;
  it("unbalanced IPv6 brackets", () => {
    expect(err("https://[::1/card")).toBeDefined();
    expect(err("https://host]/card")).toBeDefined();
    expect(err("https://[2001:db8::1]/card")).toBeUndefined();
  });
  it("brackets hold only IPv6 (zone allowed), as Python 3.12 urlsplit", () => {
    expect(err("https://[foo]/card")).toBeDefined();
    expect(err("https://[127.0.0.1]/card")).toBeDefined();
    expect(err("https://[fe80::1%25eth0]/card")).toBeUndefined();
  });
  it("NEL (U+0085) counts as whitespace", () => {
    expect(err("https://x.example/c\u0085d")).toBeDefined();
  });
});

describe("a2aFormFrom tolerates malformed YAML", () => {
  it("auth/policy that are not objects, accept_parts that is not a list", () => {
    const bad = { name: "x", type: "a2a", card_url: "https://x.example/c", auth: "KEY", policy: { accept_parts: "text" } } as unknown as ToolConfig;
    const f = a2aFormFrom(bad);
    expect(f.authKind).toBe("none");
    expect(f.accept_parts).toEqual([]);
  });
});
