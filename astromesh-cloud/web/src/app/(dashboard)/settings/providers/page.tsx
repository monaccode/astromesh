"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { Button } from "@/components/ui/Button";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ProviderStatus {
  id: string;
  name: string;
  connected: boolean;
}

// ---------------------------------------------------------------------------
// Settings nav tabs
// ---------------------------------------------------------------------------

const SETTINGS_TABS = [
  { label: "General", href: "/settings" },
  { label: "API Keys", href: "/settings/keys" },
  { label: "Providers", href: "/settings/providers" },
];

function SettingsTabs({ active }: { active: string }) {
  return (
    <div className="flex gap-1 border-b border-am-border mb-8">
      {SETTINGS_TABS.map((tab) => {
        const isActive = active === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={
              isActive
                ? "px-4 py-2.5 text-sm font-medium text-am-cyan border-b-2 border-am-cyan -mb-px"
                : "px-4 py-2.5 text-sm text-am-text-dim hover:text-am-text transition-colors"
            }
          >
            {tab.label}
          </Link>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Provider metadata
// ---------------------------------------------------------------------------

const PROVIDER_META: Record<string, { label: string; icon: string; placeholder: string }> = {
  openai: {
    label: "OpenAI",
    icon: "⬡",
    placeholder: "sk-…",
  },
  anthropic: {
    label: "Anthropic",
    icon: "✦",
    placeholder: "sk-ant-…",
  },
  google: {
    label: "Google",
    icon: "⌬",
    placeholder: "AIza…",
  },
};

const PROVIDER_IDS = ["openai", "anthropic", "google"];

// ---------------------------------------------------------------------------
// Provider card
// ---------------------------------------------------------------------------

function ProviderCard({
  provider,
  connected,
  orgSlug,
  onStatusChange,
}: {
  provider: string;
  connected: boolean;
  orgSlug: string;
  onStatusChange: () => void;
}) {
  const meta = PROVIDER_META[provider] ?? {
    label: provider,
    icon: "●",
    placeholder: "API key…",
  };

  const [showInput, setShowInput] = useState(false);
  const [keyValue, setKeyValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function handleSave() {
    if (!keyValue.trim()) {
      setError("Key cannot be empty.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.saveProviderKey(orgSlug, provider, keyValue.trim());
      setKeyValue("");
      setShowInput(false);
      onStatusChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save key.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      await api.deleteProviderKey(orgSlug, provider);
      onStatusChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove key.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="rounded-xl border border-am-border bg-am-surface p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-am-border bg-am-bg text-xl">
            {meta.icon}
          </div>
          <div>
            <p className="text-sm font-semibold text-am-text">{meta.label}</p>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span
                className={
                  connected
                    ? "h-1.5 w-1.5 rounded-full bg-am-cyan"
                    : "h-1.5 w-1.5 rounded-full bg-am-text-dim/40"
                }
              />
              <span
                className={
                  connected
                    ? "text-xs text-am-cyan"
                    : "text-xs text-am-text-dim"
                }
              >
                {connected ? "Connected" : "Not connected"}
              </span>
            </div>
          </div>
        </div>

        <div className="flex gap-2">
          {connected && (
            <Button
              size="sm"
              variant="danger"
              loading={deleting}
              onClick={handleDelete}
            >
              Remove
            </Button>
          )}
          <Button
            size="sm"
            variant={connected ? "secondary" : "primary"}
            onClick={() => {
              setShowInput((v) => !v);
              setError(null);
              setKeyValue("");
            }}
          >
            {connected ? "Update Key" : "Add Key"}
          </Button>
        </div>
      </div>

      {/* Key input */}
      {showInput && (
        <div className="space-y-3 pt-2 border-t border-am-border">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-am-text-dim uppercase tracking-wide">
              API Key
            </label>
            <input
              type="password"
              placeholder={meta.placeholder}
              value={keyValue}
              onChange={(e) => setKeyValue(e.target.value)}
              autoComplete="new-password"
              className="w-full rounded-md bg-am-bg border border-am-border px-3 py-2 text-sm text-am-text placeholder:text-am-text-dim focus:outline-none focus:ring-2 focus:ring-am-cyan focus:border-transparent transition-all"
            />
          </div>
          {error && <p className="text-xs text-am-red">{error}</p>}
          <div className="flex gap-2">
            <Button size="sm" loading={saving} onClick={handleSave}>
              Save
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setShowInput(false);
                setKeyValue("");
                setError(null);
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ProvidersPage() {
  const orgSlug = useAuthStore((s) => s.orgSlug);

  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProviders = useCallback(async () => {
    if (!orgSlug) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.listProviders(orgSlug);
      // Ensure all three built-in providers appear even if the API omits some
      const apiMap = new Map(
        (data as ProviderStatus[]).map((p) => [p.id, p])
      );
      const merged: ProviderStatus[] = PROVIDER_IDS.map((id) =>
        apiMap.get(id) ?? { id, name: PROVIDER_META[id]?.label ?? id, connected: false }
      );
      setProviders(merged);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load providers.");
    } finally {
      setLoading(false);
    }
  }, [orgSlug]);

  useEffect(() => {
    fetchProviders();
  }, [fetchProviders]);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-am-text">Settings</h1>
        <p className="mt-0.5 text-sm text-am-text-dim">Manage your organisation</p>
      </div>

      <SettingsTabs active="/settings/providers" />

      {error && (
        <div className="mb-6 rounded-lg border border-am-red/20 bg-am-red/5 px-4 py-3 text-sm text-am-red">
          {error}
          <button
            onClick={fetchProviders}
            className="ml-3 underline underline-offset-2 hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}

      <div className="mb-4">
        <p className="text-sm text-am-text-dim">
          Add provider API keys to enable the corresponding models in your agents.
          Keys are stored encrypted and never exposed after saving.
        </p>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 animate-pulse">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-28 rounded-xl bg-am-surface border border-am-border" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {providers.map((p) => (
            <ProviderCard
              key={p.id}
              provider={p.id}
              connected={p.connected}
              orgSlug={orgSlug!}
              onStatusChange={fetchProviders}
            />
          ))}
        </div>
      )}
    </div>
  );
}
