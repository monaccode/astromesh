# Astromesh Cloud Studio (Next.js) — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Next.js web app — login, agent wizard, agent management dashboard, settings, and usage overview — using the Astromesh brand palette.

**Architecture:** Next.js 14+ App Router with Tailwind CSS, NextAuth.js for OAuth, Zustand for state, React Hook Form for the wizard. All data fetched from Cloud API at `localhost:8001`.

**Tech Stack:** Next.js 14, TypeScript, Tailwind CSS, NextAuth.js, Zustand, React Hook Form, Lucide icons

**Depends on:** Cloud API plan (Tasks 1-13) must be completed first.

---

## File Structure

```
astromesh-cloud/web/
├── src/
│   ├── app/
│   │   ├── layout.tsx                    # Root layout (font, theme, providers)
│   │   ├── page.tsx                      # Redirect to /agents or /login
│   │   ├── (auth)/
│   │   │   ├── login/page.tsx            # Login page (Google/GitHub buttons)
│   │   │   └── callback/page.tsx         # OAuth callback handler
│   │   └── (dashboard)/
│   │       ├── layout.tsx                # Dashboard shell (sidebar, header)
│   │       ├── agents/
│   │       │   ├── page.tsx              # Agent list
│   │       │   └── [name]/page.tsx       # Agent detail
│   │       ├── studio/
│   │       │   ├── page.tsx              # Create new agent (wizard)
│   │       │   └── [name]/page.tsx       # Edit agent (wizard)
│   │       ├── settings/
│   │       │   ├── page.tsx              # Org settings
│   │       │   ├── keys/page.tsx         # API keys
│   │       │   └── providers/page.tsx    # Provider keys
│   │       └── usage/page.tsx            # Usage dashboard
│   ├── components/
│   │   ├── wizard/
│   │   │   ├── WizardShell.tsx           # Wizard container (steps, progress, preview)
│   │   │   ├── StepIdentity.tsx          # Step 1: name, prompt, tone
│   │   │   ├── StepModel.tsx             # Step 2: model selection
│   │   │   ├── StepTools.tsx             # Step 3: tool catalog
│   │   │   ├── StepSettings.tsx          # Step 4: memory, guardrails, orchestration
│   │   │   └── StepDeploy.tsx            # Step 5: preview, test, deploy
│   │   ├── agent/
│   │   │   ├── AgentCard.tsx             # Agent card for list view
│   │   │   └── AgentStatus.tsx           # Status badge (draft/deployed/paused)
│   │   ├── chat/
│   │   │   └── TestChat.tsx              # Inline chat for testing agents
│   │   └── ui/
│   │       ├── Button.tsx                # Primary button component
│   │       ├── Card.tsx                  # Card container
│   │       ├── Input.tsx                 # Text input
│   │       ├── Toggle.tsx                # Toggle switch
│   │       ├── Badge.tsx                 # Status/tag badges
│   │       └── Sidebar.tsx              # Dashboard sidebar nav
│   ├── lib/
│   │   ├── api.ts                        # API client (fetch wrapper with auth headers)
│   │   ├── auth.ts                       # NextAuth config
│   │   └── store.ts                      # Zustand store (wizard state, user)
│   └── styles/
│       └── globals.css                   # Tailwind directives + brand overrides
├── public/
│   └── astromesh-logo.png
├── package.json
├── tailwind.config.ts
├── next.config.ts
├── tsconfig.json
└── Dockerfile
```

---

### Task 1: Next.js Project Scaffold

**Files:**
- Create: `astromesh-cloud/web/package.json`
- Create: `astromesh-cloud/web/tsconfig.json`
- Create: `astromesh-cloud/web/next.config.ts`
- Create: `astromesh-cloud/web/tailwind.config.ts`
- Create: `astromesh-cloud/web/postcss.config.mjs`
- Create: `astromesh-cloud/web/src/styles/globals.css`
- Create: `astromesh-cloud/web/src/app/layout.tsx`
- Create: `astromesh-cloud/web/src/app/page.tsx`

- [ ] **Step 1: Initialize Next.js project**

```bash
cd astromesh-cloud && npx create-next-app@latest web --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --no-git
```

- [ ] **Step 2: Install dependencies**

```bash
cd astromesh-cloud/web && npm install zustand react-hook-form lucide-react next-auth@^4
```

- [ ] **Step 3: Configure Tailwind with Astromesh brand palette**

```typescript
// tailwind.config.ts
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
```

- [ ] **Step 4: Configure globals.css**

```css
/* src/styles/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    @apply bg-am-bg text-am-text;
  }
}
```

- [ ] **Step 5: Create root layout**

```tsx
// src/app/layout.tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Astromesh Cloud",
  description: "AI Agent Platform for Teams",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased min-h-screen">{children}</body>
    </html>
  );
}
```

- [ ] **Step 6: Create landing redirect**

```tsx
// src/app/page.tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";

export default function Home() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    if (token) {
      router.replace("/agents");
    } else {
      router.replace("/login");
    }
  }, [token, router]);

  return null;
}
```

- [ ] **Step 7: Verify dev server starts**

Run: `cd astromesh-cloud/web && npm run dev`
Expected: Next.js running at `http://localhost:3000`

- [ ] **Step 8: Commit**

```bash
git add astromesh-cloud/web/
git commit -m "feat(studio): scaffold Next.js project with Tailwind + Astromesh brand palette"
```

---

### Task 2: API Client and Auth Store

**Files:**
- Create: `src/lib/api.ts`
- Create: `src/lib/store.ts`

- [ ] **Step 1: Create API client**

```typescript
// src/lib/api.ts
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

class ApiClient {
  private token: string | null = null;

  setToken(token: string) {
    this.token = token;
  }

  clearToken() {
    this.token = null;
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };
    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const res = await fetch(`${API_URL}${path}`, { ...options, headers });

    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(error.detail || `API error: ${res.status}`);
    }

    return res.json();
  }

  // Auth
  devLogin(email: string, name: string) {
    return this.request<{ access_token: string; refresh_token: string }>(
      `/api/v1/auth/dev/login?email=${encodeURIComponent(email)}&name=${encodeURIComponent(name)}`,
      { method: "POST" }
    );
  }

  // Agents
  listAgents(slug: string) {
    return this.request<any[]>(`/api/v1/orgs/${slug}/agents`);
  }

  createAgent(slug: string, config: any) {
    return this.request(`/api/v1/orgs/${slug}/agents`, {
      method: "POST",
      body: JSON.stringify({ config }),
    });
  }

  getAgent(slug: string, name: string) {
    return this.request(`/api/v1/orgs/${slug}/agents/${name}`);
  }

  deployAgent(slug: string, name: string) {
    return this.request(`/api/v1/orgs/${slug}/agents/${name}/deploy`, { method: "POST" });
  }

  pauseAgent(slug: string, name: string) {
    return this.request(`/api/v1/orgs/${slug}/agents/${name}/pause`, { method: "POST" });
  }

  deleteAgent(slug: string, name: string) {
    return this.request(`/api/v1/orgs/${slug}/agents/${name}`, { method: "DELETE" });
  }

  runAgent(slug: string, name: string, query: string, sessionId = "default") {
    return this.request<{ answer: string; steps: any[] }>(
      `/api/v1/orgs/${slug}/agents/${name}/run`,
      { method: "POST", body: JSON.stringify({ query, session_id: sessionId }) }
    );
  }

  // Org
  getMyOrg() {
    return this.request<{ id: string; slug: string; name: string }>(`/api/v1/orgs/me`);
  }

  // Usage
  getUsage(slug: string, days = 30) {
    return this.request(`/api/v1/orgs/${slug}/usage?days=${days}`);
  }

  // Keys
  listApiKeys(slug: string) {
    return this.request<any[]>(`/api/v1/orgs/${slug}/keys`);
  }

  createApiKey(slug: string, name: string, scopes: string[]) {
    return this.request(`/api/v1/orgs/${slug}/keys`, {
      method: "POST",
      body: JSON.stringify({ name, scopes }),
    });
  }

  // Providers
  listProviders(slug: string) {
    return this.request<any[]>(`/api/v1/orgs/${slug}/providers`);
  }

  saveProviderKey(slug: string, provider: string, key: string) {
    return this.request(`/api/v1/orgs/${slug}/providers`, {
      method: "POST",
      body: JSON.stringify({ provider, key }),
    });
  }
}

export const api = new ApiClient();

// Rehydrate token from Zustand persist on page load
if (typeof window !== "undefined") {
  const stored = localStorage.getItem("astromesh-auth");
  if (stored) {
    try {
      const { state } = JSON.parse(stored);
      if (state?.token) {
        api.setToken(state.token);
      }
    } catch {}
  }
}

// Subscribe to future token changes
import { useAuthStore } from "./store";
useAuthStore.subscribe((state) => {
  if (state.token) {
    api.setToken(state.token);
  } else {
    api.clearToken();
  }
});
```

- [ ] **Step 2: Create Zustand store**

```typescript
// src/lib/store.ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  user: { email: string; name: string } | null;
  orgSlug: string | null;
  setAuth: (token: string, user: { email: string; name: string }, orgSlug: string) => void;
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
    { name: "astromesh-auth" }
  )
);

// Wizard state
interface WizardState {
  step: number;
  config: {
    name: string;
    display_name: string;
    system_prompt: string;
    tone: string;
    model: string;
    routing_strategy: string;
    tools: string[];
    tool_configs: Record<string, Record<string, unknown>>;
    memory_enabled: boolean;
    pii_filter: boolean;
    content_filter: boolean;
    orchestration: string;
  };
  setStep: (step: number) => void;
  updateConfig: (partial: Partial<WizardState["config"]>) => void;
  resetWizard: () => void;
}

const DEFAULT_CONFIG: WizardState["config"] = {
  name: "",
  display_name: "",
  system_prompt: "",
  tone: "professional",
  model: "ollama/llama3",
  routing_strategy: "cost_optimized",
  tools: [],
  tool_configs: {},
  memory_enabled: false,
  pii_filter: false,
  content_filter: false,
  orchestration: "react",
};

export const useWizardStore = create<WizardState>((set) => ({
  step: 1,
  config: { ...DEFAULT_CONFIG },
  setStep: (step) => set({ step }),
  updateConfig: (partial) =>
    set((state) => ({ config: { ...state.config, ...partial } })),
  resetWizard: () => set({ step: 1, config: { ...DEFAULT_CONFIG } }),
}));
```

- [ ] **Step 3: Commit**

```bash
git add astromesh-cloud/web/src/lib/
git commit -m "feat(studio): add API client and Zustand stores (auth + wizard)"
```

---

### Task 3: UI Primitives

**Files:**
- Create: `src/components/ui/Button.tsx`
- Create: `src/components/ui/Card.tsx`
- Create: `src/components/ui/Input.tsx`
- Create: `src/components/ui/Toggle.tsx`
- Create: `src/components/ui/Badge.tsx`
- Create: `src/components/ui/Sidebar.tsx`

- [ ] **Step 1: Create all UI primitives**

These are simple Tailwind-styled components using the `am-*` color tokens. Each is a small file (15-40 lines) with consistent props patterns: `className` merge, `variant` prop, `forwardRef` where appropriate.

Key design decisions:
- `Button`: variants `primary` (cyan bg), `secondary` (border only), `danger` (red)
- `Card`: dark surface bg, border, optional hover glow
- `Toggle`: cyan accent when active
- `Badge`: variants for `draft` (gray), `deployed` (green), `paused` (amber)
- `Sidebar`: fixed left nav with logo, nav links, org selector

- [ ] **Step 2: Commit**

```bash
git add astromesh-cloud/web/src/components/ui/
git commit -m "feat(studio): add UI primitive components (Button, Card, Input, Toggle, Badge, Sidebar)"
```

---

### Task 4: Login Page

**Files:**
- Create: `src/app/(auth)/login/page.tsx`

- [ ] **Step 1: Create login page**

```tsx
// src/app/(auth)/login/page.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";

export default function LoginPage() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);

  const handleDevLogin = async () => {
    setLoading(true);
    try {
      const result = await api.devLogin(email, name);
      api.setToken(result.access_token);

      const org = await api.getMyOrg();
      setAuth(result.access_token, { email, name }, org.slug);
      router.push("/agents");
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-full max-w-sm space-y-6 p-8 rounded-xl bg-am-surface border border-am-border">
        <div className="text-center">
          <h1 className="text-2xl font-bold">Astromesh Cloud</h1>
          <p className="text-am-text-dim text-sm mt-1">Sign in to your workspace</p>
        </div>

        {/* OAuth buttons — placeholder for v1 */}
        <button
          disabled
          className="w-full py-2.5 rounded-lg bg-white/5 border border-am-border text-am-text-dim text-sm cursor-not-allowed"
        >
          Continue with Google (coming soon)
        </button>
        <button
          disabled
          className="w-full py-2.5 rounded-lg bg-white/5 border border-am-border text-am-text-dim text-sm cursor-not-allowed"
        >
          Continue with GitHub (coming soon)
        </button>

        <div className="border-t border-am-border pt-4">
          <p className="text-xs text-am-text-dim mb-3">Dev Login</p>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full mb-2 px-3 py-2 rounded-lg bg-am-bg border border-am-border text-sm text-am-text"
          />
          <input
            type="text"
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full mb-3 px-3 py-2 rounded-lg bg-am-bg border border-am-border text-sm text-am-text"
          />
          <button
            onClick={handleDevLogin}
            disabled={loading || !email || !name}
            className="w-full py-2.5 rounded-lg bg-am-cyan text-am-bg font-semibold text-sm hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "Signing in..." : "Dev Login"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add astromesh-cloud/web/src/app/\(auth\)/
git commit -m "feat(studio): add login page with dev login and OAuth placeholders"
```

---

### Task 5: Dashboard Layout (Sidebar + Header)

**Files:**
- Create: `src/app/(dashboard)/layout.tsx`

- [ ] **Step 1: Create dashboard layout with sidebar**

The layout includes:
- Fixed left sidebar with: logo, nav links (Agents, Studio, Settings, Usage), org name at bottom
- Top header with user avatar and logout
- Main content area with max-width constraint
- Auth guard: redirects to `/login` if no token

- [ ] **Step 2: Commit**

```bash
git add astromesh-cloud/web/src/app/\(dashboard\)/layout.tsx
git commit -m "feat(studio): add dashboard layout with sidebar navigation"
```

---

### Task 6: Agent List Page

**Files:**
- Create: `src/app/(dashboard)/agents/page.tsx`
- Create: `src/components/agent/AgentCard.tsx`
- Create: `src/components/agent/AgentStatus.tsx`

- [ ] **Step 1: Create agent card and status components**

`AgentCard`: Displays agent name, display name, status badge, model, created date. Hover glow effect. Click navigates to detail. Actions: deploy/pause/delete.

`AgentStatus`: Badge variants — `draft` (gray border), `deployed` (green with pulse dot), `paused` (amber).

- [ ] **Step 2: Create agent list page**

Fetches agents from API on mount, displays grid of `AgentCard`s. "Create Agent" button navigates to `/studio`. Empty state with illustration.

- [ ] **Step 3: Commit**

```bash
git add astromesh-cloud/web/src/app/\(dashboard\)/agents/ astromesh-cloud/web/src/components/agent/
git commit -m "feat(studio): add agent list page with cards and status badges"
```

---

### Task 7: Agent Wizard — Steps 1-4

**Files:**
- Create: `src/components/wizard/WizardShell.tsx`
- Create: `src/components/wizard/StepIdentity.tsx`
- Create: `src/components/wizard/StepModel.tsx`
- Create: `src/components/wizard/StepTools.tsx`
- Create: `src/components/wizard/StepSettings.tsx`
- Create: `src/app/(dashboard)/studio/page.tsx`

- [ ] **Step 1: Create WizardShell**

Layout: left panel = step content, right panel = live config preview (YAML). Top progress bar showing 5 steps with labels. Previous/Next buttons at bottom.

Uses `useWizardStore` for state. Validates each step before allowing next.

- [ ] **Step 2: Create StepIdentity**

Fields: Agent name (auto-slug), display name, system prompt textarea, tone selector (4 visual cards: Professional, Casual, Technical, Empathetic — each with icon and color).

- [ ] **Step 3: Create StepModel**

Model cards in a grid. Two sections: "Included (Free)" and "BYOK". Each card shows: provider logo placeholder, model name, description. Selected card has cyan border glow. Routing strategy selector below as 3 radio-style cards.

- [ ] **Step 4: Create StepTools**

Tool catalog grid. Each tool: icon, name, description, toggle switch. Available tools have full color. "Coming Soon" tools are dimmed with badge. Toggles store in wizard state `tools` array.

- [ ] **Step 5: Create StepSettings**

Three sections:
- Memory: single toggle "Remember conversations"
- Guardrails: two toggles (PII filter, content filter) with descriptions
- Orchestration: three radio cards ("Respond directly", "Think step by step", "Plan before acting") with icons and descriptions

- [ ] **Step 6: Create studio page**

```tsx
// src/app/(dashboard)/studio/page.tsx
"use client";
import { WizardShell } from "@/components/wizard/WizardShell";

export default function StudioPage() {
  return <WizardShell />;
}
```

- [ ] **Step 7: Commit**

```bash
git add astromesh-cloud/web/src/components/wizard/ astromesh-cloud/web/src/app/\(dashboard\)/studio/
git commit -m "feat(studio): add 5-step agent wizard (identity, model, tools, settings)"
```

---

### Task 8: Agent Wizard — Step 5 (Preview, Test, Deploy)

**Files:**
- Create: `src/components/wizard/StepDeploy.tsx`
- Create: `src/components/chat/TestChat.tsx`

- [ ] **Step 1: Create StepDeploy**

Three sections:
1. YAML preview (collapsible `<pre>` with syntax highlighting using the wizard config → config_builder equivalent in JS)
2. "Test Agent" button → opens TestChat panel
3. "Deploy" button → calls API, shows success state with endpoint URL + code snippets

Post-deploy shows:
- API endpoint: `POST /api/v1/orgs/{slug}/agents/{name}/run`
- curl snippet
- Python ADK snippet
- JavaScript fetch snippet

Each snippet in a tabbed code block with copy button.

- [ ] **Step 2: Create TestChat**

Minimal chat UI:
- Messages list (user + assistant bubbles)
- Input field + send button
- Calls `api.testAgent()` (the test endpoint `POST /orgs/{slug}/agents/{name}/test`) — this works with `draft` agents and cleans up test memory automatically
- Loading spinner while waiting
- The API client needs a `testAgent()` method added:
  ```typescript
  testAgent(slug: string, name: string) {
    return this.request<{ answer: string }>(`/api/v1/orgs/${slug}/agents/${name}/test`, { method: "POST" });
  }
  ```

- [ ] **Step 3: Commit**

```bash
git add astromesh-cloud/web/src/components/wizard/StepDeploy.tsx astromesh-cloud/web/src/components/chat/
git commit -m "feat(studio): add deploy step with YAML preview, test chat, and code snippets"
```

---

### Task 9: Edit Agent Wizard

**Files:**
- Create: `src/app/(dashboard)/studio/[name]/page.tsx`

- [ ] **Step 1: Create edit page**

This page reuses `WizardShell` but loads an existing agent's config:
- Fetches agent via `api.getAgent(slug, name)`
- Populates `useWizardStore` with the existing config
- Changes "Deploy" button to "Update & Re-deploy" which calls `api.updateAgent()` then optionally `api.deployAgent()`
- Back navigation returns to agent detail, not agent list

- [ ] **Step 2: Add `updateAgent` to API client**

```typescript
updateAgent(slug: string, name: string, config: any) {
  return this.request(`/api/v1/orgs/${slug}/agents/${name}`, {
    method: "PUT",
    body: JSON.stringify({ config }),
  });
}
```

- [ ] **Step 3: Commit**

```bash
git add astromesh-cloud/web/src/app/\(dashboard\)/studio/\[name\]/
git commit -m "feat(studio): add edit agent wizard page"
```

---

### Task 10: Settings Pages (Org, API Keys, Providers)

**Files:**
- Create: `src/app/(dashboard)/settings/page.tsx`
- Create: `src/app/(dashboard)/settings/keys/page.tsx`
- Create: `src/app/(dashboard)/settings/providers/page.tsx`

- [ ] **Step 1: Org settings page**

Display org name (editable), member list, invite form. Member limit shown as `{count}/3`.

- [ ] **Step 2: API keys page**

Table of existing keys (prefix, name, scopes, created). "Create Key" button → modal with name + scope selector. Shows full key once on creation with copy button and warning "This key will only be shown once."

- [ ] **Step 3: Providers page**

Cards for each provider (OpenAI, Anthropic, Google). Each shows: connected/not connected status, "Add Key" button → modal with masked input. Delete button for existing keys.

- [ ] **Step 4: Commit**

```bash
git add astromesh-cloud/web/src/app/\(dashboard\)/settings/
git commit -m "feat(studio): add settings pages (org, API keys, provider keys)"
```

---

### Task 11: Usage Dashboard

**Files:**
- Create: `src/app/(dashboard)/usage/page.tsx`

- [ ] **Step 1: Create usage page**

Summary cards at top: Total Requests, Tokens In, Tokens Out, Estimated Cost. Period selector (7d, 30d, 90d).

Table below with per-agent breakdown (agent name, requests, tokens, cost). Basic bar chart representation using CSS (no chart library in v1).

- [ ] **Step 2: Commit**

```bash
git add astromesh-cloud/web/src/app/\(dashboard\)/usage/
git commit -m "feat(studio): add usage dashboard with summary cards and period selector"
```

---

### Task 12: Dockerfile and Final Integration

**Files:**
- Create: `astromesh-cloud/web/Dockerfile`
- Modify: `astromesh-cloud/docker-compose.yaml`

- [ ] **Step 1: Create production Dockerfile**

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

- [ ] **Step 2: Update next.config.ts for standalone output**

```typescript
// next.config.ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
```

- [ ] **Step 3: Verify Docker build**

Run: `cd astromesh-cloud/web && docker build -t astromesh-studio .`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add astromesh-cloud/web/Dockerfile astromesh-cloud/web/next.config.ts
git commit -m "feat(studio): add Dockerfile and standalone build config"
```

---

## Summary

| Task | What it delivers |
|------|-----------------|
| 1 | Next.js scaffold with Tailwind + Astromesh brand |
| 2 | API client + Zustand stores (auth, wizard) |
| 3 | UI primitive components |
| 4 | Login page (dev login + OAuth placeholders) |
| 5 | Dashboard layout with sidebar |
| 6 | Agent list page with cards |
| 7 | Wizard steps 1-4 (identity, model, tools, settings) |
| 8 | Wizard step 5 (preview, test chat, deploy) |
| 9 | Edit agent wizard page |
| 10 | Settings pages (org, keys, providers) |
| 11 | Usage dashboard |
| 12 | Dockerfile + Docker integration |

After these 12 tasks, the full Astromesh Cloud v1 is functional: users can log in, create/edit agents via the wizard, deploy them, test via chat, manage API keys, and view usage.
