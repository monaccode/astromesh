export interface AgentMeta {
  name: string;
  version: string;
  namespace: string;
  description: string;
  status: "draft" | "deployed" | "paused";
}

/** A model candidate. Core selects the adapter by `source` (new) or `provider` (legacy). */
export interface ModelConfig {
  provider?: string;
  source?: string;
  /** ProviderConfig entry name; inherits source/endpoint/model from the registry. */
  providerRef?: string;
  model?: string;
  context_window?: number;
  endpoint?: string;
  api_key_env?: string;
  parameters?: {
    temperature?: number;
    top_p?: number;
    max_tokens?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface ModelRole {
  candidates: ModelConfig[];
  strategy?: string;
  [key: string]: unknown;
}

export interface ToolConfig {
  name: string;
  type: "builtin" | "agent";
  /** Target agent name; required by the runtime when `type` is "agent". */
  agent?: string;
  description: string;
  parameters?: Record<string, { type: string; description: string }>;
}

export interface GuardrailConfig {
  type: string;
  action?: "redact" | "block" | "warn" | "truncate";
  message?: string;
  blocked_topics?: string[];
  max_chars?: number;
  blocked_patterns?: string[];
  forbidden_keywords?: string[];
  max_tokens_per_turn?: number;
  count?: "output" | "total";
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
    /** Legacy `primary`/`fallback`/`routing`, or per-role `default` + `roles` (core 0.29+). */
    model: {
      primary?: ModelConfig;
      fallback?: ModelConfig;
      routing?: {
        strategy: string;
        health_check_interval?: number;
      };
      default?: ModelRole;
      roles?: Record<string, ModelRole>;
      [key: string]: unknown;
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
    knowledge?: { pipeline?: string; top_k?: number; bundle?: string };
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
