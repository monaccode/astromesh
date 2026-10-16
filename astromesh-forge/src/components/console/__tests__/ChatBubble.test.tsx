import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ChatBubble } from "../ChatBubble";
import type { RunRecord } from "../../../types/console";

const run: RunRecord = {
  id: "r1",
  agentName: "a",
  query: "q",
  answer: "No puedo ayudar con eso.",
  timestamp: 0,
  durationMs: 1000,
  usage: {
    tokens_in: 10,
    tokens_out: 5,
    model: "m",
    by_model: [
      { provider: "ollama", model: "m", role: "default", calls: 1, tokens_in: 10, tokens_out: 5, tokens_cached: 7, cost: 0 },
    ],
  },
  trace: null,
  steps: [],
  blocked: true,
  guardrail: { direction: "input", rule: "topic_filter", reason: "blocked topic" },
  propuestas: [{ tool: "crm_create", tipo: "integration", destino: "crm", operacion: "create", argumentos: { x: 1 } }],
};

describe("ChatBubble (core 0.70 run fields)", () => {
  it("shows guardrail block, proposed writes and cached tokens", () => {
    render(
      <ChatBubble message={{ id: "m", role: "assistant", content: run.answer, timestamp: 0, runId: "r1" }} run={run} />,
    );
    expect(screen.getByText(/Blocked by guardrail/)).toBeInTheDocument();
    expect(screen.getByText(/input topic_filter: blocked topic/)).toBeInTheDocument();
    expect(screen.getByText(/1 proposed write \(not executed\)/)).toBeInTheDocument();
    expect(screen.getByText("7 cached")).toBeInTheDocument();
  });
});
