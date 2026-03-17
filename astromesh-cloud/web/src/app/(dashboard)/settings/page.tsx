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

interface OrgMember {
  id: string;
  name: string;
  email: string;
  role: string;
}

interface OrgData {
  slug: string;
  name: string;
  plan?: string;
  memberCount?: number;
  maxMembers?: number;
  members?: OrgMember[];
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
// Role badge
// ---------------------------------------------------------------------------

function RoleBadge({ role }: { role: string }) {
  const isOwner = role === "owner";
  return (
    <span
      className={
        isOwner
          ? "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold bg-am-cyan/20 text-am-cyan border border-am-cyan/30"
          : "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold bg-white/5 text-am-text-dim border border-am-border"
      }
    >
      {role}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function OrgSettingsPage() {
  const orgSlug = useAuthStore((s) => s.orgSlug);

  const [org, setOrg] = useState<OrgData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Org name edit state
  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);

  // Invite form state
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteSuccess, setInviteSuccess] = useState<string | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);

  const fetchOrg = useCallback(async () => {
    if (!orgSlug) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getMyOrg();
      setOrg(data as OrgData);
      setNameValue((data as OrgData).name ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load org settings.");
    } finally {
      setLoading(false);
    }
  }, [orgSlug]);

  useEffect(() => {
    fetchOrg();
  }, [fetchOrg]);

  async function handleSaveName() {
    if (!orgSlug || !nameValue.trim()) return;
    setSavingName(true);
    setNameError(null);
    try {
      await api.updateOrg(orgSlug, { name: nameValue.trim() });
      setOrg((prev) => (prev ? { ...prev, name: nameValue.trim() } : prev));
      setEditingName(false);
    } catch (err) {
      setNameError(err instanceof Error ? err.message : "Failed to save.");
    } finally {
      setSavingName(false);
    }
  }

  async function handleInvite() {
    if (!orgSlug || !inviteEmail.trim()) return;
    setInviteLoading(true);
    setInviteError(null);
    setInviteSuccess(null);
    try {
      await api.inviteMember(orgSlug, inviteEmail.trim());
      setInviteSuccess(`Invite sent to ${inviteEmail.trim()}`);
      setInviteEmail("");
    } catch (err) {
      setInviteError(err instanceof Error ? err.message : "Failed to send invite.");
    } finally {
      setInviteLoading(false);
    }
  }

  const memberCount = org?.memberCount ?? org?.members?.length ?? 0;
  const maxMembers = org?.maxMembers ?? 5;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-am-text">Settings</h1>
        <p className="mt-0.5 text-sm text-am-text-dim">Manage your organisation</p>
      </div>

      <SettingsTabs active="/settings" />

      {error && (
        <div className="mb-6 rounded-lg border border-am-red/20 bg-am-red/5 px-4 py-3 text-sm text-am-red">
          {error}
          <button onClick={fetchOrg} className="ml-3 underline underline-offset-2 hover:no-underline">
            Retry
          </button>
        </div>
      )}

      {loading ? (
        <div className="space-y-4 animate-pulse">
          <div className="h-24 rounded-xl bg-am-surface border border-am-border" />
          <div className="h-48 rounded-xl bg-am-surface border border-am-border" />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Org name card */}
          <div className="rounded-xl border border-am-border bg-am-surface p-6">
            <h2 className="mb-4 text-sm font-semibold text-am-text uppercase tracking-wide">
              Organisation
            </h2>
            <div className="flex items-end gap-3">
              {editingName ? (
                <>
                  <Input
                    label="Organisation name"
                    value={nameValue}
                    onChange={(e) => setNameValue(e.target.value)}
                    error={nameError ?? undefined}
                    className="max-w-xs"
                  />
                  <div className="flex gap-2 pb-0.5">
                    <Button size="sm" loading={savingName} onClick={handleSaveName}>
                      Save
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setEditingName(false);
                        setNameValue(org?.name ?? "");
                        setNameError(null);
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <p className="text-xs font-medium text-am-text-dim uppercase tracking-wide mb-1">
                      Organisation name
                    </p>
                    <p className="text-sm font-medium text-am-text">{org?.name ?? orgSlug}</p>
                    <p className="text-xs text-am-text-dim mt-0.5">Slug: {org?.slug ?? orgSlug}</p>
                  </div>
                  <Button size="sm" variant="secondary" onClick={() => setEditingName(true)}>
                    Edit
                  </Button>
                </>
              )}
            </div>
          </div>

          {/* Members card */}
          <div className="rounded-xl border border-am-border bg-am-surface p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-am-text uppercase tracking-wide">
                Members
              </h2>
              <span className="text-xs text-am-text-dim">
                {memberCount}/{maxMembers} members
              </span>
            </div>

            {org?.members && org.members.length > 0 ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left border-b border-am-border">
                    <th className="pb-2 text-xs font-medium text-am-text-dim uppercase tracking-wide">
                      Name
                    </th>
                    <th className="pb-2 text-xs font-medium text-am-text-dim uppercase tracking-wide">
                      Email
                    </th>
                    <th className="pb-2 text-xs font-medium text-am-text-dim uppercase tracking-wide">
                      Role
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {org.members.map((member) => (
                    <tr key={member.id} className="border-b border-am-border/50 last:border-0">
                      <td className="py-3 text-am-text">{member.name || "—"}</td>
                      <td className="py-3 text-am-text-dim">{member.email}</td>
                      <td className="py-3">
                        <RoleBadge role={member.role} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-sm text-am-text-dim">No members found.</p>
            )}

            {/* Invite form */}
            <div className="mt-6 pt-5 border-t border-am-border">
              <h3 className="mb-3 text-xs font-semibold text-am-text-dim uppercase tracking-wide">
                Invite member
              </h3>
              <div className="flex items-end gap-3">
                <Input
                  label="Email address"
                  type="email"
                  placeholder="colleague@example.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="max-w-xs"
                />
                <Button
                  size="sm"
                  loading={inviteLoading}
                  onClick={handleInvite}
                  disabled={!inviteEmail.trim()}
                >
                  Send Invite
                </Button>
              </div>
              {inviteSuccess && (
                <p className="mt-2 text-xs text-am-cyan">{inviteSuccess}</p>
              )}
              {inviteError && (
                <p className="mt-2 text-xs text-am-red">{inviteError}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
