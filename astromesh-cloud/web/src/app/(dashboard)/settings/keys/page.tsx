"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  createdAt: string;
}

// ---------------------------------------------------------------------------
// Settings nav tabs (duplicated here to keep pages self-contained)
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
// Available scopes
// ---------------------------------------------------------------------------

const ALL_SCOPES = ["agents:read", "agents:write", "agents:run", "admin"];

// ---------------------------------------------------------------------------
// Newly-created key banner
// ---------------------------------------------------------------------------

function NewKeyBanner({ keyValue, onDismiss }: { keyValue: string; onDismiss: () => void }) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(keyValue).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="rounded-xl border border-am-cyan/30 bg-am-cyan/5 p-5 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-am-cyan mb-1">API key created</p>
          <p className="text-xs text-am-text-dim">
            This key will only be shown once. Copy it now and store it securely.
          </p>
        </div>
        <button
          onClick={onDismiss}
          className="text-am-text-dim hover:text-am-text transition-colors text-lg leading-none mt-0.5"
          aria-label="Dismiss"
        >
          ×
        </button>
      </div>
      <div className="flex items-center gap-2">
        <code className="flex-1 rounded-md bg-am-bg border border-am-border px-3 py-2 text-xs font-mono text-am-text break-all">
          {keyValue}
        </code>
        <Button size="sm" variant="secondary" onClick={copy}>
          {copied ? "Copied!" : "Copy"}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create key form
// ---------------------------------------------------------------------------

function CreateKeyForm({
  onCreated,
  onCancel,
  orgSlug,
}: {
  onCreated: (key: string) => void;
  onCancel: () => void;
  orgSlug: string;
}) {
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["agents:read", "agents:run"]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleScope(scope: string) {
    setScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope]
    );
  }

  async function handleCreate() {
    if (!name.trim()) {
      setError("Key name is required.");
      return;
    }
    if (scopes.length === 0) {
      setError("Select at least one scope.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await api.createApiKey(orgSlug, name.trim(), scopes);
      const fullKey = (result as { key?: string }).key ?? "";
      onCreated(fullKey);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create key.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-xl border border-am-border bg-am-surface p-5 space-y-4">
      <h3 className="text-sm font-semibold text-am-text">New API key</h3>

      <Input
        label="Key name"
        placeholder="e.g. CI deploy key"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="max-w-xs"
      />

      <div>
        <p className="mb-2 text-xs font-medium text-am-text-dim uppercase tracking-wide">
          Scopes
        </p>
        <div className="flex flex-wrap gap-2">
          {ALL_SCOPES.map((scope) => {
            const active = scopes.includes(scope);
            return (
              <button
                key={scope}
                onClick={() => toggleScope(scope)}
                className={
                  active
                    ? "rounded-full px-3 py-1 text-xs font-medium bg-am-cyan/20 text-am-cyan border border-am-cyan/40 transition-all"
                    : "rounded-full px-3 py-1 text-xs font-medium bg-am-bg text-am-text-dim border border-am-border hover:border-am-border-hover transition-all"
                }
              >
                {scope}
              </button>
            );
          })}
        </div>
      </div>

      {error && <p className="text-xs text-am-red">{error}</p>}

      <div className="flex gap-2">
        <Button size="sm" loading={loading} onClick={handleCreate}>
          Create Key
        </Button>
        <Button size="sm" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ApiKeysPage() {
  const orgSlug = useAuthStore((s) => s.orgSlug);

  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newKeyValue, setNewKeyValue] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchKeys = useCallback(async () => {
    if (!orgSlug) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.listApiKeys(orgSlug);
      setKeys(data as ApiKey[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load API keys.");
    } finally {
      setLoading(false);
    }
  }, [orgSlug]);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  function handleKeyCreated(keyValue: string) {
    setNewKeyValue(keyValue);
    setShowCreate(false);
    fetchKeys();
  }

  async function handleDelete(keyId: string) {
    if (!orgSlug) return;
    setDeletingId(keyId);
    try {
      await api.deleteApiKey(orgSlug, keyId);
      setKeys((prev) => prev.filter((k) => k.id !== keyId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete key.");
    } finally {
      setDeletingId(null);
    }
  }

  function formatDate(iso: string) {
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return iso;
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-am-text">Settings</h1>
        <p className="mt-0.5 text-sm text-am-text-dim">Manage your organisation</p>
      </div>

      <SettingsTabs active="/settings/keys" />

      {error && (
        <div className="mb-6 rounded-lg border border-am-red/20 bg-am-red/5 px-4 py-3 text-sm text-am-red">
          {error}
          <button onClick={fetchKeys} className="ml-3 underline underline-offset-2 hover:no-underline">
            Retry
          </button>
        </div>
      )}

      {/* Newly created key banner */}
      {newKeyValue && (
        <div className="mb-6">
          <NewKeyBanner keyValue={newKeyValue} onDismiss={() => setNewKeyValue(null)} />
        </div>
      )}

      <div className="rounded-xl border border-am-border bg-am-surface p-6">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-am-text uppercase tracking-wide">
            API Keys
          </h2>
          {!showCreate && (
            <Button size="sm" onClick={() => setShowCreate(true)}>
              + Create Key
            </Button>
          )}
        </div>

        {/* Create form */}
        {showCreate && orgSlug && (
          <div className="mb-6">
            <CreateKeyForm
              orgSlug={orgSlug}
              onCreated={handleKeyCreated}
              onCancel={() => setShowCreate(false)}
            />
          </div>
        )}

        {/* Keys table */}
        {loading ? (
          <div className="space-y-3 animate-pulse">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 rounded bg-white/5" />
            ))}
          </div>
        ) : keys.length === 0 ? (
          <p className="text-sm text-am-text-dim py-6 text-center">
            No API keys yet. Create one above to get started.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-am-border text-left">
                <th className="pb-2 text-xs font-medium text-am-text-dim uppercase tracking-wide">Prefix</th>
                <th className="pb-2 text-xs font-medium text-am-text-dim uppercase tracking-wide">Name</th>
                <th className="pb-2 text-xs font-medium text-am-text-dim uppercase tracking-wide">Scopes</th>
                <th className="pb-2 text-xs font-medium text-am-text-dim uppercase tracking-wide">Created</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => (
                <tr key={key.id} className="border-b border-am-border/50 last:border-0">
                  <td className="py-3 font-mono text-xs text-am-text-dim">
                    {key.prefix}…
                  </td>
                  <td className="py-3 text-am-text">{key.name}</td>
                  <td className="py-3">
                    <div className="flex flex-wrap gap-1">
                      {(key.scopes ?? []).map((s) => (
                        <span
                          key={s}
                          className="rounded-full bg-am-cyan/10 border border-am-cyan/20 px-2 py-0.5 text-xs text-am-cyan"
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="py-3 text-xs text-am-text-dim whitespace-nowrap">
                    {formatDate(key.createdAt)}
                  </td>
                  <td className="py-3 text-right">
                    <Button
                      size="sm"
                      variant="danger"
                      loading={deletingId === key.id}
                      onClick={() => handleDelete(key.id)}
                    >
                      Delete
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
