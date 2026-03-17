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
  const [error, setError] = useState<string | null>(null);

  async function handleDevLogin(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !name.trim()) {
      setError("Email and name are required.");
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const loginRes = await api.devLogin(email.trim(), name.trim());
      api.setToken(loginRes.token);
      const org = await api.getMyOrg();
      setAuth(loginRes.token, loginRes.user, org.slug);
      router.push("/agents");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-am-bg flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo / Title */}
        <div className="mb-8 text-center">
          <span className="font-mono text-xs font-bold tracking-widest text-am-cyan uppercase">
            Astromesh Cloud
          </span>
          <h1 className="mt-2 text-2xl font-semibold text-am-text">Sign in to your workspace</h1>
          <p className="mt-1 text-sm text-am-text-dim">AI agent platform for teams</p>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-am-border bg-am-surface p-6 space-y-6">
          {/* Social logins — coming soon */}
          <div className="space-y-2">
            <button
              disabled
              className="w-full flex items-center justify-center gap-2 rounded-md border border-am-border bg-am-surface px-4 py-2.5 text-sm text-am-text-dim cursor-not-allowed opacity-50"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
              </svg>
              Continue with Google
              <span className="ml-1 text-xs opacity-60">(coming soon)</span>
            </button>

            <button
              disabled
              className="w-full flex items-center justify-center gap-2 rounded-md border border-am-border bg-am-surface px-4 py-2.5 text-sm text-am-text-dim cursor-not-allowed opacity-50"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
              Continue with GitHub
              <span className="ml-1 text-xs opacity-60">(coming soon)</span>
            </button>
          </div>

          {/* Divider */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-am-border" />
            <span className="text-xs text-am-text-dim">dev login</span>
            <div className="flex-1 h-px bg-am-border" />
          </div>

          {/* Dev Login form */}
          <form onSubmit={handleDevLogin} className="space-y-3">
            <div>
              <label className="block text-xs text-am-text-dim mb-1" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full rounded-md border border-am-border bg-am-bg px-3 py-2 text-sm text-am-text placeholder-am-text-dim focus:outline-none focus:border-am-cyan transition-colors"
              />
            </div>

            <div>
              <label className="block text-xs text-am-text-dim mb-1" htmlFor="name">
                Name
              </label>
              <input
                id="name"
                type="text"
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your Name"
                className="w-full rounded-md border border-am-border bg-am-bg px-3 py-2 text-sm text-am-text placeholder-am-text-dim focus:outline-none focus:border-am-cyan transition-colors"
              />
            </div>

            {error && (
              <p className="text-xs text-am-red rounded-md border border-am-red/20 bg-am-red/5 px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-md bg-am-cyan px-4 py-2.5 text-sm font-semibold text-am-bg hover:bg-am-cyan/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>

        <p className="mt-4 text-center text-xs text-am-text-dim">
          Astromesh Cloud &mdash; AI Agent Platform
        </p>
      </div>
    </div>
  );
}
