import type { AgentConfig, AgentMeta } from "../types/agent";
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
    return this.#request("/v1/agents");
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

  async listTools(): Promise<{ name: string; description: string }[]> {
    return this.#request("/v1/tools/builtin");
  }
}
