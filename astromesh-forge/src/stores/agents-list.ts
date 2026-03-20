import { create } from "zustand";
import type { AgentMeta } from "../types/agent";

interface AgentsListState {
  agents: AgentMeta[];
  loading: boolean;
  error: string | null;
  setAgents: (agents: AgentMeta[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useAgentsListStore = create<AgentsListState>((set) => ({
  agents: [],
  loading: false,
  error: null,
  setAgents: (agents) => set({ agents, error: null }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error, loading: false }),
}));
