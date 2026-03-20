export interface AgentMeta {
  name: string;
  version: string;
  namespace: string;
  description: string;
  status: "draft" | "deployed" | "paused";
}

export interface ModelConfig {
  provider: string;
  model: string;
  endpoint?: string;
  api_key_env?: string;
  parameters?: {
    temperature?: number;
    top_p?: number;
    max_tokens?: number;
  };
}

export interface ToolConfig {
  name: string;
  type: "internal" | "mcp" | "webhook" | "rag" | "agent";
  description: string;
  parameters?: Record<string, { type: string; description: string }>;
}

export interface GuardrailConfig {
  type: string;
  action?: "redact" | "block";
  [key: string]: unknown;
}

export interface MemoryConfig {
  backend: string;
  strategy?: string;
  max_turns?: number;
  ttl?: number;
  similarity_threshold?: number;
  max_results?: number;
}

export interface AgentConfig {
  apiVersion: string;
  kind: "Agent";
  metadata: {
    name: string;
    version: string;
    namespace?: string;
    labels?: Record<string, string>;
  };
  spec: {
    identity: {
      display_name: string;
      description: string;
      avatar?: string;
    };
    model: {
      primary: ModelConfig;
      fallback?: ModelConfig;
      routing?: {
        strategy: string;
        health_check_interval?: number;
      };
    };
    prompts: {
      system: string;
      templates?: Record<string, string>;
    };
    orchestration: {
      pattern: string;
      max_iterations: number;
      timeout_seconds?: number;
    };
    tools?: ToolConfig[];
    memory?: {
      conversational?: MemoryConfig;
      semantic?: MemoryConfig;
      episodic?: MemoryConfig;
    };
    guardrails?: {
      input?: GuardrailConfig[];
      output?: GuardrailConfig[];
    };
    permissions?: {
      allowed_actions?: string[];
      filesystem?: { read?: string[]; write?: string[] };
      network?: { allowed?: string[] };
      execution?: { dry_run?: boolean };
    };
  };
}
