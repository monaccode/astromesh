import { create } from "zustand";
import { ForgeClient } from "../api/client";

interface ConnectionState {
  nodeUrl: string;
  connected: boolean;
  checking: boolean;
  client: ForgeClient;
  setNodeUrl: (url: string) => void;
  checkConnection: () => Promise<void>;
}

const DEFAULT_URL = import.meta.env.VITE_ASTROMESH_URL || "http://localhost:8000";

export const useConnectionStore = create<ConnectionState>((set, get) => ({
  nodeUrl: DEFAULT_URL,
  connected: false,
  checking: false,
  client: new ForgeClient(DEFAULT_URL),
  setNodeUrl: (url: string) => {
    set({ nodeUrl: url, client: new ForgeClient(url), connected: false });
    get().checkConnection();
  },
  checkConnection: async () => {
    set({ checking: true });
    const healthy = await get().client.healthCheck();
    set({ connected: healthy, checking: false });
  },
}));
