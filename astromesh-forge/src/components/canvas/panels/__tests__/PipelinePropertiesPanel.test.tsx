import { render, fireEvent, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { Node } from "@xyflow/react";
import { PipelinePropertiesPanel } from "../PipelinePropertiesPanel";

function applyFor(id: string, type: string, config: Record<string, unknown>) {
  const onApply = vi.fn();
  const node = { id, type, position: { x: 0, y: 0 }, data: { label: id, category: type, config } } as Node;
  render(<PipelinePropertiesPanel node={node} onApply={onApply} onRemove={() => {}} onClose={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Apply" }));
  return onApply.mock.calls[0][1].config;
}

describe("PipelinePropertiesPanel keeps keys it does not edit", () => {
  it("tool, without writing a description core ignores", () => {
    const cfg = { name: "crm", type: "integration", connection: "hubspot", actions: ["a"], max_result_tokens: 50 };
    expect(applyFor("tool-0-crm", "tool", cfg)).toEqual(cfg);
  });

  it("offers api/mcp only to a tool that already is that type", () => {
    applyFor("tool-0-x", "tool", { name: "x", type: "builtin" });
    const opts = [...(screen.getByLabelText("Type") as HTMLSelectElement).options].map((o) => o.value);
    expect(opts).not.toContain("api");
    expect(opts).not.toContain("mcp");
  });

  it("keeps api type selectable on an api tool", () => {
    applyFor("tool-0-w", "tool", { name: "w", type: "api", operations: [] });
    const opts = [...(screen.getByLabelText("Type") as HTMLSelectElement).options].map((o) => o.value);
    expect(opts).toContain("api");
    expect(opts).not.toContain("mcp");
  });

  it("offers a2a to a new (builtin) tool", () => {
    applyFor("tool-0-x", "tool", { name: "x", type: "builtin" });
    const opts = [...(screen.getByLabelText("Type") as HTMLSelectElement).options].map((o) => o.value);
    expect(opts).toContain("a2a");
  });

  it("keeps an existing a2a tool unchanged", () => {
    const cfg = {
      name: "ag",
      type: "a2a",
      card_url: "https://x.example/card.json",
      auth: { api_key_env: "KEY" },
      policy: { max_bytes: 1024, accept_parts: ["text"] },
      rate_limit: { calls: 1, period: 1 },
    };
    expect(applyFor("tool-0-ag", "tool", cfg)).toEqual(cfg);
  });

  it("model", () => {
    const cfg = { source: "litellm", model: "x/y", context_window: 9000, timeout: 5, parameters: { top_p: 0.5 } };
    expect(applyFor("model-primary", "model", cfg)).toEqual({
      ...cfg,
      parameters: { top_p: 0.5, temperature: 0.7 },
    });
  });

  it("memory", () => {
    const cfg = { backend: "redis", connection: { url: "redis://x" }, max_turns: 5 };
    const out = applyFor("memory-conv", "memory", cfg);
    expect(out.connection).toEqual({ url: "redis://x" });
    expect(out.backend).toBe("redis");
  });

  it("memory without connection gets none", () => {
    const out = applyFor("memory-sem", "memory", { backend: "chromadb", max_results: 3 });
    expect("connection" in out).toBe(false);
  });
});

describe("PipelinePropertiesPanel a2a form", () => {
  function renderTool(config: Record<string, unknown>) {
    const onApply = vi.fn();
    const node = { id: "tool-0", type: "tool", position: { x: 0, y: 0 }, data: { label: "t", category: "tool", config } } as Node;
    render(<PipelinePropertiesPanel node={node} onApply={onApply} onRemove={() => {}} onClose={() => {}} />);
    return onApply;
  }
  const type = (label: string | RegExp, value: string) =>
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  const apply = () => fireEvent.click(screen.getByRole("button", { name: "Apply" }));

  it("blocks Apply and shows inline errors on an invalid a2a tool", () => {
    const onApply = renderTool({ name: "remote", type: "builtin" });
    type("Type", "a2a");
    type("Agent card URL", "http://localhost:9000/card.json");
    type("Auth", "bearer_env");
    type("Bearer token environment variable name", "sk-live-123");
    type("Timeout (seconds)", "601");
    apply();
    expect(onApply).not.toHaveBeenCalled();
    expect(screen.getByText(/Must be https/)).toBeTruthy();
    expect(screen.getByText(/letters, digits and _/)).toBeTruthy();
    expect(screen.getByText(/≤ 600 seconds/)).toBeTruthy();
  });

  it("creates an a2a tool from a builtin one with the core keys", () => {
    const onApply = renderTool({ name: "remote", type: "builtin" });
    type("Type", "a2a");
    expect(screen.getByLabelText(/Description/).getAttribute("placeholder")).toMatch(/remote agent's card/);
    type("Agent card URL", "http://localhost:9000/card.json");
    fireEvent.click(screen.getByLabelText(/Allow insecure http/));
    type("Auth", "api_key_env");
    type("API key environment variable name", "AGENDA_KEY");
    type("Max response bytes", "262144");
    fireEvent.click(screen.getByLabelText("data"));
    apply();
    expect(onApply.mock.calls[0][1].config).toEqual({
      name: "remote",
      type: "a2a",
      card_url: "http://localhost:9000/card.json",
      auth: { api_key_env: "AGENDA_KEY" },
      policy: { max_bytes: 262144, accept_parts: ["data"], allow_insecure_http: true },
    });
  });
});
