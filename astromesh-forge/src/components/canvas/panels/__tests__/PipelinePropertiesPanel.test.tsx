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
