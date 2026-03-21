import { create } from "zustand";

export interface Toast {
  id: string;
  type: "success" | "error" | "info" | "warning";
  message: string;
}

interface ToastStore {
  toasts: Toast[];
  addToast: (message: string, type: Toast["type"]) => void;
  removeToast: (id: string) => void;
}

let counter = 0;

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  addToast: (message, type) => {
    const id = `toast-${++counter}`;
    set((s) => ({
      toasts: [...s.toasts.slice(-4), { id, type, message }],
    }));
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, 4000);
  },
  removeToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
