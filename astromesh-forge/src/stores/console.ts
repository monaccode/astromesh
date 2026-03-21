import { create } from "zustand";
import type { AgentConfig } from "../types/agent";
import type {
  ChatMessage,
  CompareSelection,
  ParameterOverrides,
  RunRecord,
} from "../types/console";
import { useConnectionStore } from "./connection";

interface ConsoleState {
  selectedAgent: string | null;
  agentConfig: AgentConfig | null;
  overrides: ParameterOverrides;
  messages: ChatMessage[];
  sessionId: string;
  running: boolean;
  error: string | null;
  runs: RunRecord[];
  activeTraceRunId: string | null;
  compareSelection: CompareSelection;

  selectAgent: (name: string) => Promise<void>;
  setOverride: <K extends keyof ParameterOverrides>(
    key: K,
    value: ParameterOverrides[K],
  ) => void;
  sendMessage: (query: string) => Promise<void>;
  viewTrace: (runId: string) => void;
  setCompare: (selection: CompareSelection) => void;
  clearChat: () => void;
  resetSession: () => void;
}

function generateId(): string {
  return crypto.randomUUID();
}

export const useConsoleStore = create<ConsoleState>((set, get) => ({
  selectedAgent: null,
  agentConfig: null,
  overrides: { disabledTools: [] },
  messages: [],
  sessionId: generateId(),
  running: false,
  error: null,
  runs: [],
  activeTraceRunId: null,
  compareSelection: null,

  selectAgent: async (name: string) => {
    const client = useConnectionStore.getState().client;
    try {
      const config = await client.getAgent(name);
      set({
        selectedAgent: name,
        agentConfig: config,
        overrides: { disabledTools: [] },
        error: null,
      });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : "Failed to load agent" });
    }
  },

  setOverride: (key, value) =>
    set((state) => ({
      overrides: { ...state.overrides, [key]: value },
    })),

  sendMessage: async (query: string) => {
    const { selectedAgent, sessionId, overrides } = get();
    if (!selectedAgent) return;

    const client = useConnectionStore.getState().client;
    const userMsg: ChatMessage = {
      id: generateId(),
      role: "user",
      content: query,
      timestamp: Date.now(),
    };

    set((state) => ({
      messages: [...state.messages, userMsg],
      running: true,
      error: null,
    }));

    const startTime = Date.now();
    try {
      const context: Record<string, unknown> = {};
      if (overrides.model) context.model_override = overrides.model;
      if (overrides.temperature !== undefined)
        context.temperature = overrides.temperature;
      if (overrides.max_tokens !== undefined)
        context.max_tokens = overrides.max_tokens;
      if (overrides.disabledTools.length > 0)
        context.disabled_tools = overrides.disabledTools;

      const response = await client.runAgent(
        selectedAgent,
        query,
        sessionId,
        Object.keys(context).length > 0 ? context : undefined,
      );

      const runId = generateId();
      const durationMs = Date.now() - startTime;

      const run: RunRecord = {
        id: runId,
        agentName: selectedAgent,
        query,
        answer: response.answer,
        timestamp: startTime,
        durationMs,
        usage: response.usage,
        trace: response.trace,
        steps: response.steps,
      };

      const assistantMsg: ChatMessage = {
        id: generateId(),
        role: "assistant",
        content: response.answer,
        timestamp: Date.now(),
        runId,
      };

      set((state) => ({
        messages: [...state.messages, assistantMsg],
        runs: [...state.runs, run],
        activeTraceRunId: runId,
        running: false,
      }));
    } catch (e) {
      set({
        running: false,
        error: e instanceof Error ? e.message : "Agent run failed",
      });
    }
  },

  viewTrace: (runId: string) => set({ activeTraceRunId: runId }),

  setCompare: (selection: CompareSelection) =>
    set({ compareSelection: selection }),

  clearChat: () =>
    set({
      messages: [],
      runs: [],
      activeTraceRunId: null,
      compareSelection: null,
      error: null,
    }),

  resetSession: () =>
    set({
      messages: [],
      runs: [],
      activeTraceRunId: null,
      compareSelection: null,
      error: null,
      sessionId: generateId(),
      overrides: { disabledTools: [] },
    }),
}));
