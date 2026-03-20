import { describe, it, expect, beforeEach, vi } from "vitest";
import { ForgeClient } from "../client";

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

describe("ForgeClient", () => {
  let client: ForgeClient;

  beforeEach(() => {
    client = new ForgeClient("http://localhost:8000");
    mockFetch.mockReset();
  });

  it("lists agents", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([{ name: "test", status: "deployed" }]),
    });
    const agents = await client.listAgents();
    expect(agents).toHaveLength(1);
    expect(mockFetch).toHaveBeenCalledWith("http://localhost:8000/v1/agents", expect.any(Object));
  });

  it("creates agent", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "created" }),
    });
    const config = { apiVersion: "astromesh/v1", kind: "Agent" } as any;
    await client.createAgent(config);
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/v1/agents",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("deploys agent", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "deployed" }),
    });
    await client.deployAgent("test");
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/v1/agents/test/deploy",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("lists templates", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([{ name: "sales-qualifier" }]),
    });
    const templates = await client.listTemplates();
    expect(templates).toHaveLength(1);
  });

  it("checks health", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "ok" }),
    });
    const healthy = await client.healthCheck();
    expect(healthy).toBe(true);
  });

  it("returns false on health check failure", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Connection refused"));
    const healthy = await client.healthCheck();
    expect(healthy).toBe(false);
  });
});
