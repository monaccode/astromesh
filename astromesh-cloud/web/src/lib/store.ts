import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "@/lib/api";

// ---------------------------------------------------------------------------
// Auth store
// ---------------------------------------------------------------------------

interface User {
  email: string;
  name: string;
}

interface AuthState {
  token: string | null;
  user: User | null;
  orgSlug: string | null;
  setAuth: (token: string, user: User, orgSlug: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      orgSlug: null,

      setAuth: (token, user, orgSlug) => set({ token, user, orgSlug }),

      logout: () => set({ token: null, user: null, orgSlug: null }),
    }),
    {
      name: "astromesh-auth",
    }
  )
);

// Keep the API client token in sync with auth store changes.
useAuthStore.subscribe((state) => {
  if (state.token) api.setToken(state.token);
  else api.clearToken();
});

// ---------------------------------------------------------------------------
// Wizard store
// ---------------------------------------------------------------------------

export interface WizardConfig {
  // Step 1 — Agent identity
  agentName: string;
  displayName: string;
  description: string;

  // Step 2 — Model & routing
  provider: string;
  model: string;
  routingStrategy: string;
  fallbackModel: string;

  // Step 3 — Personality & prompts
  systemPrompt: string;
  tone: string;

  // Step 4 — Tools & memory
  tools: string[];
  memoryType: string;
  memoryStrategy: string;

  // Step 5 — Deploy
  channel: string;
  guardrailsEnabled: boolean;
  maxIterations: number;
}

const defaultWizardConfig: WizardConfig = {
  agentName: "",
  displayName: "",
  description: "",
  provider: "openai",
  model: "gpt-4o-mini",
  routingStrategy: "cost_optimized",
  fallbackModel: "",
  systemPrompt: "",
  tone: "professional",
  tools: [],
  memoryType: "conversational",
  memoryStrategy: "sliding_window",
  channel: "api",
  guardrailsEnabled: true,
  maxIterations: 10,
};

interface WizardState {
  step: number;
  config: WizardConfig;
  setStep: (step: number) => void;
  updateConfig: (partial: Partial<WizardConfig>) => void;
  resetWizard: () => void;
}

export const useWizardStore = create<WizardState>()((set) => ({
  step: 1,
  config: { ...defaultWizardConfig },

  setStep: (step) => set({ step }),

  updateConfig: (partial) =>
    set((state) => ({ config: { ...state.config, ...partial } })),

  resetWizard: () => set({ step: 1, config: { ...defaultWizardConfig } }),
}));
