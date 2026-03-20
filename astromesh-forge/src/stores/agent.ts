import { create } from "zustand";
import type { AgentConfig } from "../types/agent";

const EMPTY_CONFIG: AgentConfig = {
  apiVersion: "astromesh/v1",
  kind: "Agent",
  metadata: { name: "", version: "1.0.0" },
  spec: {
    identity: { display_name: "", description: "" },
    model: {
      primary: {
        provider: "ollama",
        model: "llama3.1:8b",
        endpoint: "http://ollama:11434",
      },
      routing: { strategy: "cost_optimized" },
    },
    prompts: { system: "" },
    orchestration: { pattern: "react", max_iterations: 10 },
  },
};

interface AgentEditorState {
  config: AgentConfig;
  dirty: boolean;
  templateOrigin: string | null;
  setConfig: (config: AgentConfig) => void;
  updateSpec: <K extends keyof AgentConfig["spec"]>(
    key: K,
    value: AgentConfig["spec"][K]
  ) => void;
  reset: () => void;
  loadFromTemplate: (config: AgentConfig, templateName: string) => void;
}

export const useAgentEditorStore = create<AgentEditorState>((set) => ({
  config: structuredClone(EMPTY_CONFIG),
  dirty: false,
  templateOrigin: null,
  setConfig: (config) => set({ config, dirty: true }),
  updateSpec: (key, value) =>
    set((state) => ({
      config: {
        ...state.config,
        spec: { ...state.config.spec, [key]: value },
      },
      dirty: true,
    })),
  reset: () =>
    set({
      config: structuredClone(EMPTY_CONFIG),
      dirty: false,
      templateOrigin: null,
    }),
  loadFromTemplate: (config, templateName) =>
    set({ config, dirty: false, templateOrigin: templateName }),
}));
