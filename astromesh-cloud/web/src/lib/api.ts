const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface RunAgentResponse {
  response: string;
  session_id: string;
  [key: string]: unknown;
}

interface AgentConfig {
  [key: string]: unknown;
}

interface ApiKeyOptions {
  name: string;
  scopes: string[];
}

class ApiClient {
  private token: string | null = null;

  setToken(token: string): void {
    this.token = token;
  }

  clearToken(): void {
    this.token = null;
  }

  private headers(): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (this.token) h["Authorization"] = `Bearer ${this.token}`;
    return h;
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown
  ): Promise<T> {
    const res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: this.headers(),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(`API ${method} ${path} failed (${res.status}): ${text}`);
    }

    return res.json() as Promise<T>;
  }

  // ---------------------------------------------------------------------------
  // Auth
  // ---------------------------------------------------------------------------

  devLogin(email: string, name: string) {
    return this.request<{ token: string; user: { email: string; name: string }; org_slug: string }>(
      "POST",
      "/api/v1/auth/dev/login",
      { email, name }
    );
  }

  // ---------------------------------------------------------------------------
  // Org
  // ---------------------------------------------------------------------------

  getMyOrg() {
    return this.request<{ slug: string; name: string; [key: string]: unknown }>(
      "GET",
      "/api/v1/orgs/me"
    );
  }

  getUsage(slug: string, days = 30) {
    return this.request<Record<string, unknown>>(
      "GET",
      `/api/v1/orgs/${slug}/usage?days=${days}`
    );
  }

  // ---------------------------------------------------------------------------
  // Agents
  // ---------------------------------------------------------------------------

  listAgents(slug: string) {
    return this.request<unknown[]>("GET", `/api/v1/orgs/${slug}/agents`);
  }

  createAgent(slug: string, config: AgentConfig) {
    return this.request<unknown>("POST", `/api/v1/orgs/${slug}/agents`, config);
  }

  getAgent(slug: string, name: string) {
    return this.request<unknown>("GET", `/api/v1/orgs/${slug}/agents/${name}`);
  }

  deployAgent(slug: string, name: string) {
    return this.request<unknown>(
      "POST",
      `/api/v1/orgs/${slug}/agents/${name}/deploy`
    );
  }

  pauseAgent(slug: string, name: string) {
    return this.request<unknown>(
      "POST",
      `/api/v1/orgs/${slug}/agents/${name}/pause`
    );
  }

  deleteAgent(slug: string, name: string) {
    return this.request<unknown>(
      "DELETE",
      `/api/v1/orgs/${slug}/agents/${name}`
    );
  }

  runAgent(
    slug: string,
    name: string,
    query: string,
    sessionId?: string
  ): Promise<RunAgentResponse> {
    return this.request<RunAgentResponse>(
      "POST",
      `/api/v1/orgs/${slug}/agents/${name}/run`,
      { query, session_id: sessionId }
    );
  }

  testAgent(slug: string, name: string) {
    return this.request<RunAgentResponse>(
      "POST",
      `/api/v1/orgs/${slug}/agents/${name}/test`
    );
  }

  // ---------------------------------------------------------------------------
  // API Keys
  // ---------------------------------------------------------------------------

  listApiKeys(slug: string) {
    return this.request<unknown[]>("GET", `/api/v1/orgs/${slug}/api-keys`);
  }

  createApiKey(slug: string, name: string, scopes: string[]) {
    return this.request<ApiKeyOptions & { key: string }>(
      "POST",
      `/api/v1/orgs/${slug}/api-keys`,
      { name, scopes }
    );
  }

  // ---------------------------------------------------------------------------
  // Providers
  // ---------------------------------------------------------------------------

  listProviders(slug: string) {
    return this.request<unknown[]>("GET", `/api/v1/orgs/${slug}/providers`);
  }

  saveProviderKey(slug: string, provider: string, key: string) {
    return this.request<unknown>(
      "POST",
      `/api/v1/orgs/${slug}/providers/${provider}/key`,
      { key }
    );
  }
}

export const api = new ApiClient();

// Rehydrate token from Zustand persist
if (typeof window !== "undefined") {
  try {
    const stored = localStorage.getItem("astromesh-auth");
    if (stored) {
      const { state } = JSON.parse(stored) as { state?: { token?: string } };
      if (state?.token) api.setToken(state.token);
    }
  } catch {
    // ignore parse errors
  }
}
