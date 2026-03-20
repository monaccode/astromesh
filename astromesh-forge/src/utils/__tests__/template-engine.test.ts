import { describe, it, expect } from "vitest";
import { resolveTemplate, resolveTemplateObject } from "../template-engine";

describe("resolveTemplate", () => {
  it("replaces simple variables", () => {
    const result = resolveTemplate("Hello {{name}}", { name: "World" });
    expect(result).toBe("Hello World");
  });

  it("applies slugify filter", () => {
    const result = resolveTemplate("{{company|slugify}}", { company: "Acme Corp" });
    expect(result).toBe("acme-corp");
  });

  it("applies lower filter", () => {
    const result = resolveTemplate("{{text|lower}}", { text: "HELLO" });
    expect(result).toBe("hello");
  });

  it("applies upper filter", () => {
    const result = resolveTemplate("{{text|upper}}", { text: "hello" });
    expect(result).toBe("HELLO");
  });

  it("keeps unresolved variables", () => {
    const result = resolveTemplate("{{missing}}", {});
    expect(result).toBe("{{missing}}");
  });

  it("resolves deeply nested objects", () => {
    const obj = { metadata: { name: "{{company|slugify}}-agent" } };
    const resolved = resolveTemplateObject(obj, { company: "Acme Corp" });
    expect(resolved.metadata.name).toBe("acme-corp-agent");
  });
});
