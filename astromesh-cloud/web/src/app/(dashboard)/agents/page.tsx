"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { AgentCard, AgentRecord } from "@/components/agent/AgentCard";
import { Button } from "@/components/ui/Button";

function AgentGridSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl border border-am-border bg-am-surface p-5 animate-pulse"
        >
          <div className="flex items-start justify-between mb-3">
            <div className="space-y-2 flex-1 mr-4">
              <div className="h-4 w-3/4 rounded bg-white/10" />
              <div className="h-3 w-1/2 rounded bg-white/5" />
            </div>
            <div className="h-5 w-16 rounded-full bg-white/10 shrink-0" />
          </div>
          <div className="flex gap-4 mb-5">
            <div className="h-3 w-24 rounded bg-white/5" />
            <div className="h-3 w-24 rounded bg-white/5" />
          </div>
          <div className="flex gap-2">
            <div className="h-7 flex-1 rounded bg-white/5" />
            <div className="h-7 w-16 rounded bg-white/5" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState({ onCreateClick }: { onCreateClick: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-am-border bg-am-surface text-3xl">
        ⬡
      </div>
      <h3 className="mb-1 text-base font-semibold text-am-text">No agents yet</h3>
      <p className="mb-6 max-w-xs text-sm text-am-text-dim">
        Build your first AI agent in the Studio. Configure its model, tools, and memory in
        minutes.
      </p>
      <Button onClick={onCreateClick}>Create your first agent</Button>
    </div>
  );
}

export default function AgentsPage() {
  const router = useRouter();
  const orgSlug = useAuthStore((s) => s.orgSlug);

  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    if (!orgSlug) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.listAgents(orgSlug);
      setAgents(data as AgentRecord[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents.");
    } finally {
      setLoading(false);
    }
  }, [orgSlug]);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  function handleCreateClick() {
    router.push("/studio");
  }

  return (
    <div>
      {/* Page header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-am-text">Agents</h1>
          <p className="mt-0.5 text-sm text-am-text-dim">
            Manage and deploy your AI agents
          </p>
        </div>
        <Button onClick={handleCreateClick}>+ Create Agent</Button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-6 rounded-lg border border-am-red/20 bg-am-red/5 px-4 py-3 text-sm text-am-red">
          {error}
          <button
            onClick={fetchAgents}
            className="ml-3 underline underline-offset-2 hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Content */}
      {loading ? (
        <AgentGridSkeleton />
      ) : agents.length === 0 ? (
        <EmptyState onCreateClick={handleCreateClick} />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent) => (
            <AgentCard
              key={agent.name}
              agent={agent}
              orgSlug={orgSlug!}
              onStatusChange={fetchAgents}
              onDelete={fetchAgents}
            />
          ))}
        </div>
      )}
    </div>
  );
}
