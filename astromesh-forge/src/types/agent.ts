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

/** A2A Agent Card skill declared in `spec.skills` (core 0.73+). */
export interface Skill {
  id: string;
  name: string;
  description: string;
  tags?: string[];
  examples?: string[];
  inputModes?: string[];
  outputModes?: string[];
}

export interface ToolConfig {
  name: string;
  /** Types core wires in runtime/engine.py; api/mcp/integration carry their own manifest keys. */
  type: "builtin" | "agent" | "client" | "integration" | "api" | "mcp" | "a2a";
  /** Target agent name; required by the runtime when `type` is "agent". */
  agent?: string;
  description?: string;
  parameters?: Record<string, { type: string; description: string }>;
  /** Per-tool cap on the result fed back to the model (core 0.66). */
  max_result_tokens?: number;
  /** integration: connection name and the actions to expose. */
  connection?: unknown;
  actions?: string[];
  /** a2a: remote agent card (https unless policy.allow_insecure_http). Required by core. */
  card_url?: string;
  /** a2a: env var NAMES, exactly one of api_key_env / bearer_env. Never the secret. */
  auth?: { api_key_env?: string; bearer_env?: string };
  /** a2a: limits for calls to the remote agent. */
  policy?: {
    max_bytes?: number;
    timeout?: number;
    accept_parts?: ("text" | "data" | "file")[];
    allow_insecure_http?: boolean;
  };
  [key: string]: unknown;
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
  /** `redis` (the only conversational backend core builds) requires `connection.url`. */
  connection?: { url?: string; [key: string]: unknown };
  strategy?: string;
  max_turns?: number;
  ttl?: number;
  similarity_threshold?: number;
  max_results?: number;
  [key: string]: unknown;
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
      /** Per-query template rendered apart from `system`, so the system prompt stays cacheable (0.64). */
      context?: string;
      templates?: Record<string, string>;
      [key: string]: unknown;
    };
    orchestration: {
      pattern: string;
      max_iterations: number;
      timeout_seconds?: number;
      /** `swarm`: cap on chained handoffs (integer >= 1, core default 3). */
      max_handoffs?: number;
      /** `pipeline`: 2–6 stage names. */
      stages?: string[];
      max_tool_result_tokens?: number;
      role_map?: Record<string, string>;
      [key: string]: unknown;
    };
    tools?: ToolConfig[];
    skills?: Skill[];
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
      denied_actions?: string[];
    };
    /** program (glyph), prefetch, output_schema, chain, observability… kept verbatim. */
    [key: string]: unknown;
  };
}
