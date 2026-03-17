"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UsageData {
  total_requests: number;
  tokens_in: number;
  tokens_out: number;
  estimated_cost_usd: number;
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function SummaryCardSkeleton() {
  return (
    <Card className="animate-pulse">
      <div className="mb-2 h-3 w-24 rounded bg-white/10" />
      <div className="h-8 w-32 rounded bg-white/10" />
    </Card>
  );
}

function UsageSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <SummaryCardSkeleton key={i} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary card
// ---------------------------------------------------------------------------

interface SummaryCardProps {
  label: string;
  value: string;
  sub?: string;
}

function SummaryCard({ label, value, sub }: SummaryCardProps) {
  return (
    <Card>
      <p className="mb-1 text-xs font-medium uppercase tracking-wider text-am-text-dim">
        {label}
      </p>
      <p className="text-2xl font-semibold text-am-text tabular-nums">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-am-text-dim">{sub}</p>}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Period selector
// ---------------------------------------------------------------------------

const PERIODS = [
  { label: "7d", days: 7 },
  { label: "30d", days: 30 },
  { label: "90d", days: 90 },
] as const;

type Period = (typeof PERIODS)[number]["days"];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

function formatUsd(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(n);
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function UsagePage() {
  const orgSlug = useAuthStore((s) => s.orgSlug);

  const [period, setPeriod] = useState<Period>(30);
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchUsage = useCallback(async () => {
    if (!orgSlug) return;
    setLoading(true);
    setError(null);
    try {
      const data = (await api.getUsage(orgSlug, period)) as UsageData;
      setUsage(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load usage data.");
    } finally {
      setLoading(false);
    }
  }, [orgSlug, period]);

  useEffect(() => {
    fetchUsage();
  }, [fetchUsage]);

  return (
    <div>
      {/* Page header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-am-text">Usage</h1>
          <p className="mt-0.5 text-sm text-am-text-dim">
            API consumption and cost breakdown
          </p>
        </div>

        {/* Period selector */}
        <div className="flex items-center gap-1 rounded-lg border border-am-border bg-am-surface p-1">
          {PERIODS.map(({ label, days }) => (
            <button
              key={days}
              onClick={() => setPeriod(days)}
              className={
                period === days
                  ? "rounded-md bg-am-cyan-dim px-3 py-1 text-xs font-semibold text-am-cyan transition-all"
                  : "rounded-md px-3 py-1 text-xs text-am-text-dim transition-all hover:text-am-text"
              }
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-6 rounded-lg border border-am-red/20 bg-am-red/5 px-4 py-3 text-sm text-am-red">
          {error}
          <button
            onClick={fetchUsage}
            className="ml-3 underline underline-offset-2 hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Summary cards */}
      {loading ? (
        <UsageSkeleton />
      ) : usage ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryCard
            label="Total Requests"
            value={formatNumber(usage.total_requests)}
            sub={`Last ${period} days`}
          />
          <SummaryCard
            label="Tokens In"
            value={formatNumber(usage.tokens_in)}
            sub="Input tokens"
          />
          <SummaryCard
            label="Tokens Out"
            value={formatNumber(usage.tokens_out)}
            sub="Output tokens"
          />
          <SummaryCard
            label="Estimated Cost"
            value={formatUsd(usage.estimated_cost_usd)}
            sub="USD"
          />
        </div>
      ) : null}

      {/* Empty state when no error and no data */}
      {!loading && !error && !usage && (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-am-border bg-am-surface text-3xl">
            ⌀
          </div>
          <h3 className="mb-1 text-base font-semibold text-am-text">No usage data</h3>
          <p className="mb-6 max-w-xs text-sm text-am-text-dim">
            Usage metrics will appear here once your agents start processing requests.
          </p>
          <Button variant="secondary" onClick={fetchUsage}>
            Refresh
          </Button>
        </div>
      )}
    </div>
  );
}
