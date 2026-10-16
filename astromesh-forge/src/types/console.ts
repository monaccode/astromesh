export interface SpanAttributes {
  // Identity
  agent?: string;
  session?: string;

  // LLM
  model?: string;
  provider?: string;
  input_tokens?: number;
  output_tokens?: number;
  latency_ms?: number;
  cost?: number;
  prompt?: string;
  input_messages?: string;
  query?: string;
  response?: string;
  tool_calls?: Array<{ id?: string; name: string; arguments: Record<string, unknown> }>;

  // Tool
  tool?: string;
  tool_args?: Record<string, unknown>;
  tool_result?: string;

  // Orchestration (steps are in span.events)
  pattern?: string;

  // Error
  error_message?: string;

  // Catch-all for unknown attributes
  [key: string]: unknown;
}

export interface TraceSpan {
  name: string;
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  status: "ok" | "error" | "unset";
  attributes: SpanAttributes;
  events: Array<{
    name: string;
    timestamp: number;
    attributes: Record<string, unknown>;
  }>;
  start_time: number;
  end_time: number | null;
  duration_ms: number | null;
}

export interface Trace {
  trace_id: string;
  agent: string;
  session_id: string;
  is_sampled: boolean;
  spans: TraceSpan[];
}

/** `ModelUsage` in api/routes/agents.py. */
export interface ModelUsage {
  provider: string;
  model: string;
  role: string;
  calls: number;
  tokens_in: number;
  tokens_out: number;
  tokens_cached: number;
  cost: number;
}

/** A write a `mode: propose` tool recorded instead of executing (integrations/propuestas.py). */
export interface Propuesta {
  tool: string;
  tipo: string;
  destino: string;
  operacion: string;
  argumentos: unknown;
  via?: string;
}

export interface RunResponse {
  answer: string;
  steps: Array<Record<string, unknown>>;
  usage: { tokens_in: number; tokens_out: number; model: string; by_model?: ModelUsage[] } | null;
  trace: Trace | null;
  data?: Record<string, unknown> | null;
  propuestas?: Propuesta[];
  /** True when a guardrail blocked the run; `answer` is then the refusal message. */
  blocked?: boolean;
  guardrail?: { direction: string; rule: string; reason: string } | null;
}

export interface ParameterOverrides {
  model?: string;
  temperature?: number;
  max_tokens?: number;
  disabledTools: string[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  runId?: string;
}

export interface RunRecord {
  id: string;
  agentName: string;
  query: string;
  answer: string;
  timestamp: number;
  durationMs: number;
  usage: RunResponse["usage"];
  trace: Trace | null;
  steps: Array<Record<string, unknown>>;
  blocked?: boolean;
  guardrail?: RunResponse["guardrail"];
  propuestas?: Propuesta[];
}

export type CompareSelection = [string, string] | null;
