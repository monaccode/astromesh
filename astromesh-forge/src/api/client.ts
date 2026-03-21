import type { AgentConfig, AgentMeta } from "../types/agent";
import type { RunResponse, Trace } from "../types/console";
import type { TemplateSummary, TemplateDetail } from "../types/template";

export class ForgeClient {
  #baseUrl: string;

  constructor(baseUrl: string) {
    this.#baseUrl = baseUrl;
  }

  async #request<T>(path: string, options?: RequestInit): Promise<T> {
    const resp = await fetch(`${this.#baseUrl}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${resp.status}`);
    }
    return resp.json();
  }

  async healthCheck(): Promise<boolean> {
    try {
      await this.#request("/v1/health");
      return true;
    } catch {
      return false;
    }
  }

  async listAgents(): Promise<AgentMeta[]> {
    const data = await this.#request<AgentMeta[] | { agents: AgentMeta[] }>(
      "/v1/agents"
    );
    if (Array.isArray(data)) {
      return data;
    }
    if (data && typeof data === "object" && "agents" in data) {
      return Array.isArray(data.agents) ? data.agents : [];
    }
    return [];
  }

  async getAgent(name: string): Promise<AgentConfig> {
    return this.#request(`/v1/agents/${name}`);
  }

  async createAgent(config: AgentConfig): Promise<{ status: string }> {
    return this.#request("/v1/agents", {
      method: "POST",
      body: JSON.stringify(config),
    });
  }

  async updateAgent(name: string, config: AgentConfig): Promise<{ status: string }> {
    return this.#request(`/v1/agents/${name}`, {
      method: "PUT",
      body: JSON.stringify(config),
    });
  }

  async deleteAgent(name: string): Promise<void> {
    await this.#request(`/v1/agents/${name}`, { method: "DELETE" });
  }

  async deployAgent(name: string): Promise<{ status: string }> {
    return this.#request(`/v1/agents/${name}/deploy`, { method: "POST" });
  }

  async pauseAgent(name: string): Promise<{ status: string }> {
    return this.#request(`/v1/agents/${name}/pause`, { method: "POST" });
  }

  async listTemplates(): Promise<TemplateSummary[]> {
    return this.#request("/v1/templates");
  }

  async getTemplate(name: string): Promise<TemplateDetail> {
    return this.#request(`/v1/templates/${name}`);
  }

  async runAgent(
    name: string,
    query: string,
    sessionId: string,
    context?: Record<string, unknown>,
  ): Promise<RunResponse> {
    return this.#request(`/v1/agents/${name}/run`, {
      method: "POST",
      body: JSON.stringify({ query, session_id: sessionId, context }),
    });
  }

  async getTraces(agent?: string, limit?: number): Promise<{ traces: Trace[] }> {
    const params = new URLSearchParams();
    if (agent) params.set("agent", agent);
    if (limit) params.set("limit", String(limit));
    const qs = params.toString();
    return this.#request(`/v1/traces/${qs ? `?${qs}` : ""}`);
  }

  async getTrace(traceId: string): Promise<Trace> {
    return this.#request(`/v1/traces/${traceId}`);
  }

  async listTools(): Promise<{ name: string; description: string }[]> {
    type ToolRow = { name: string; description: string };
    const data = await this.#request<
      ToolRow[] | { tools: ToolRow[]; count?: number }
    >("/v1/tools/builtin");
    if (Array.isArray(data)) {
      return data;
    }
    if (data && typeof data === "object" && "tools" in data) {
      return Array.isArray(data.tools) ? data.tools : [];
    }
    return [];
  }
}
