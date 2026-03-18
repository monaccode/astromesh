"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AgentStatus, AgentStatusValue } from "@/components/agent/AgentStatus";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";

export interface AgentRecord {
  name: string;
  display_name?: string;
  status: AgentStatusValue;
  config?: {
    spec?: {
      model?: {
        primary?: string;
      };
    };
  };
  created_at?: string;
  org_slug?: string;
}

interface AgentCardProps {
  agent: AgentRecord;
  orgSlug: string;
  onStatusChange?: () => void;
  onDelete?: () => void;
}

function formatDate(iso?: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function AgentCard({ agent, orgSlug, onStatusChange, onDelete }: AgentCardProps) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const model = agent.config?.spec?.model?.primary ?? "—";
  const isDeployed = agent.status === "deployed";

  async function handleToggle(e: React.MouseEvent) {
    e.stopPropagation();
    setBusy(true);
    try {
      if (isDeployed) {
        await api.pauseAgent(orgSlug, agent.name);
      } else {
        await api.deployAgent(orgSlug, agent.name);
      }
      onStatusChange?.();
    } catch {
      // surface error silently for now
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setBusy(true);
    try {
      await api.deleteAgent(orgSlug, agent.name);
      onDelete?.();
    } catch {
      // surface error silently for now
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  }

  function handleCardClick() {
    router.push(`/studio/${agent.name}`);
  }

  return (
    <div
      onClick={handleCardClick}
      className={cn(
        "group rounded-xl bg-am-surface border border-am-border p-5 transition-all cursor-pointer",
        "hover:border-am-border-hover hover:shadow-[0_0_20px_rgba(0,212,255,0.10)]"
      )}
    >
      {/* Top row: name + status */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="min-w-0">
          <p className="truncate font-semibold text-am-text leading-tight">
            {agent.display_name ?? agent.name}
          </p>
          <p className="mt-0.5 truncate text-xs text-am-text-dim font-mono">
            {agent.name}
          </p>
        </div>
        <AgentStatus status={agent.status} pulse={isDeployed} className="shrink-0" />
      </div>

      {/* Meta row */}
      <div className="flex items-center gap-4 text-xs text-am-text-dim mb-5">
        <span className="flex items-center gap-1">
          <span className="opacity-50">model</span>
          <span className="text-am-text font-mono">{model}</span>
        </span>
        <span className="flex items-center gap-1">
          <span className="opacity-50">created</span>
          <span>{formatDate(agent.created_at)}</span>
        </span>
      </div>

      {/* Action buttons */}
      <div
        className="flex items-center gap-2"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          disabled={busy}
          onClick={handleToggle}
          className={cn(
            "flex-1 rounded px-3 py-1.5 text-xs font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed",
            isDeployed
              ? "border border-am-amber/40 text-am-amber hover:bg-am-amber/10"
              : "border border-am-cyan/40 text-am-cyan hover:bg-am-cyan-dim"
          )}
        >
          {busy ? (
            <span className="inline-flex items-center gap-1.5">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
              {isDeployed ? "Pausing…" : "Deploying…"}
            </span>
          ) : isDeployed ? (
            "Pause"
          ) : (
            "Deploy"
          )}
        </button>

        <button
          disabled={busy}
          onClick={handleDelete}
          className={cn(
            "rounded px-3 py-1.5 text-xs font-medium border transition-all disabled:opacity-40 disabled:cursor-not-allowed",
            confirmDelete
              ? "border-am-red/60 text-am-red bg-am-red/10 hover:bg-am-red/20"
              : "border-am-border text-am-text-dim hover:border-am-red/40 hover:text-am-red"
          )}
        >
          {confirmDelete ? "Confirm?" : "Delete"}
        </button>
      </div>
    </div>
  );
}
