export interface TraceSpan {
  name: string;
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  status: "ok" | "error" | "unset";
  attributes: Record<string, unknown>;
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

export interface RunResponse {
  answer: string;
  steps: Array<Record<string, unknown>>;
  usage: { tokens_in: number; tokens_out: number; model: string } | null;
  trace: Trace | null;
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
}

export type CompareSelection = [string, string] | null;
