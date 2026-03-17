import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        am: {
          cyan: "#00d4ff",
          "cyan-dim": "rgba(0, 212, 255, 0.15)",
          "cyan-glow": "rgba(0, 212, 255, 0.35)",
          bg: "#0a0e14",
          surface: "rgba(255, 255, 255, 0.03)",
          "surface-hover": "rgba(255, 255, 255, 0.06)",
          border: "rgba(255, 255, 255, 0.08)",
          "border-hover": "rgba(0, 212, 255, 0.4)",
          text: "#e6edf3",
          "text-dim": "rgba(230, 237, 243, 0.6)",
          purple: "#8b5cf6",
          green: "#3fb950",
          amber: "#f59e0b",
          red: "#ef4444",
        },
      },
      fontFamily: {
        sans: ["DM Sans", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
