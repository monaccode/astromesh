import {
  TrendingDown,
  TrendingUp,
  Minus,
  X,
  GitCompareArrows,
} from "lucide-react";
import type { RunRecord, TraceSpan } from "../../types/console";
import { useConsoleStore } from "../../stores/console";
import { getSpanColor } from "../../utils/trace-tree";
import { useState } from "react";

interface CompareViewProps {
  runA: RunRecord;
  runB: RunRecord;
}

/** Match spans between two traces by name + order */
function matchSpans(spansA: TraceSpan[], spansB: TraceSpan[]) {
  const rows: Array<{ name: string; a?: TraceSpan; b?: TraceSpan }> = [];
  const usedB = new Set<number>();

  for (const spanA of spansA) {
    const bIdx = spansB.findIndex(
      (sb, i) => !usedB.has(i) && sb.name === spanA.name
    );
    if (bIdx !== -1) {
      usedB.add(bIdx);
      rows.push({ name: spanA.name, a: spanA, b: spansB[bIdx] });
    } else {
      rows.push({ name: spanA.name, a: spanA });
    }
  }
  for (let i = 0; i < spansB.length; i++) {
    if (!usedB.has(i)) {
      rows.push({ name: spansB[i].name, b: spansB[i] });
    }
  }
  return rows;
}

function DeltaBadge({ a, b }: { a: number; b: number }) {
  if (a === 0 && b === 0) return null;
  const delta = b - a;
  const pct = a > 0 ? ((delta / a) * 100).toFixed(0) : "—";
  const isFaster = delta < 0;
  const isSlower = delta > 0;
  const isSame = delta === 0;

  return (
    <span
      className={`inline-flex items-center gap-0.5 text-[9px] font-mono ${
        isFaster
          ? "text-emerald-400"
          : isSlower
            ? "text-red-400"
            : "text-gray-500"
      }`}
    >
      {isFaster ? (
        <TrendingDown size={10} />
      ) : isSlower ? (
        <TrendingUp size={10} />
      ) : (
        <Minus size={10} />
      )}
      {isSame ? "0ms" : `${delta > 0 ? "+" : ""}${delta.toFixed(0)}ms`}
      {pct !== "—" && !isSame && (
        <span className="opacity-60">({pct}%)</span>
      )}
    </span>
  );
}

function StatCard({
  label,
  valueA,
  valueB,
  format,
}: {
  label: string;
  valueA: number;
  valueB: number;
  format: (v: number) => string;
}) {
  const delta = valueB - valueA;
  const isBetter = delta < 0;
  const isWorse = delta > 0;

  return (
    <div className="bg-gray-800/50 rounded-lg px-3 py-2 flex-1 min-w-[120px]">
      <div className="text-[8px] uppercase tracking-wider text-gray-500 mb-1">
        {label}
      </div>
      <div className="flex items-baseline gap-3">
        <span className="text-cyan-400 text-sm font-mono">{format(valueA)}</span>
        <span className="text-gray-600">vs</span>
        <span className="text-orange-400 text-sm font-mono">{format(valueB)}</span>
      </div>
      {(valueA > 0 || valueB > 0) && (
        <div
          className={`text-[9px] mt-0.5 ${
            isBetter ? "text-emerald-400" : isWorse ? "text-red-400" : "text-gray-500"
          }`}
        >
          {delta === 0
            ? "identical"
            : `${delta > 0 ? "+" : ""}${format(delta)} (${valueA > 0 ? ((delta / valueA) * 100).toFixed(0) : "—"}%)`}
        </div>
      )}
    </div>
  );
}

function CompareSpanRow({
  name,
  a,
  b,
  maxDuration,
}: {
  name: string;
  a?: TraceSpan;
  b?: TraceSpan;
  maxDuration: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const dA = a?.duration_ms ?? 0;
  const dB = b?.duration_ms ?? 0;
  const barA = maxDuration > 0 ? (dA / maxDuration) * 100 : 0;
  const barB = maxDuration > 0 ? (dB / maxDuration) * 100 : 0;
  const isError = a?.status === "error" || b?.status === "error";

  return (
    <div className="mb-0.5">
      <div
        className={`bg-gray-800/80 rounded border-l-[3px] ${
          isError ? "border-red-500" : getSpanColor(name)
        } px-3 py-2 cursor-pointer hover:bg-gray-800 transition-colors`}
        onClick={() => setExpanded(!expanded)}
      >
        {/* Span name row */}
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-2 min-w-0">
            <span className={`text-xs font-medium truncate ${isError ? "text-red-400" : "text-gray-200"}`}>
              {name}
            </span>
            {a?.status === "ok" && (
              <span className="bg-green-500/20 text-green-400 text-[7px] px-1 rounded">OK</span>
            )}
            {a?.status === "error" && (
              <span className="bg-red-500/20 text-red-400 text-[7px] px-1 rounded">ERR</span>
            )}
          </div>
          <DeltaBadge a={dA} b={dB} />
        </div>

        {/* Dual duration bars */}
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-2">
            <span className="text-[8px] text-cyan-400 w-5 text-right font-mono">A</span>
            <div className="flex-1 bg-gray-900 rounded-sm h-[5px]">
              {a ? (
                <div
                  className="h-full rounded-sm bg-cyan-500/60"
                  style={{ width: `${Math.max(barA, 1)}%` }}
                />
              ) : (
                <div className="h-full flex items-center justify-center">
                  <span className="text-[7px] text-gray-600">—</span>
                </div>
              )}
            </div>
            <span className="text-[9px] text-gray-500 font-mono w-14 text-right">
              {a ? `${dA.toFixed(0)}ms` : "n/a"}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[8px] text-orange-400 w-5 text-right font-mono">B</span>
            <div className="flex-1 bg-gray-900 rounded-sm h-[5px]">
              {b ? (
                <div
                  className="h-full rounded-sm bg-orange-500/60"
                  style={{ width: `${Math.max(barB, 1)}%` }}
                />
              ) : (
                <div className="h-full flex items-center justify-center">
                  <span className="text-[7px] text-gray-600">—</span>
                </div>
              )}
            </div>
            <span className="text-[9px] text-gray-500 font-mono w-14 text-right">
              {b ? `${dB.toFixed(0)}ms` : "n/a"}
            </span>
          </div>
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (a || b) && (
        <div className="ml-4 mt-0.5 mb-1 bg-gray-950 rounded p-2.5 text-[9px] flex gap-4">
          {a && (
            <div className="flex-1 border-l-2 border-cyan-500/30 pl-2">
              <div className="text-[8px] text-cyan-400 uppercase mb-1 font-semibold">Run A</div>
              <SpanDetail span={a} />
            </div>
          )}
          {b && (
            <div className="flex-1 border-l-2 border-orange-500/30 pl-2">
              <div className="text-[8px] text-orange-400 uppercase mb-1 font-semibold">Run B</div>
              <SpanDetail span={b} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SpanDetail({ span }: { span: TraceSpan }) {
  const attrs = span.attributes;
  const inputTokens = attrs.input_tokens as number | undefined;
  const outputTokens = attrs.output_tokens as number | undefined;
  const tool = attrs.tool as string | undefined;
  const toolResult = attrs.tool_result as unknown;

  return (
    <div className="flex flex-col gap-1 text-gray-400">
      {(inputTokens != null || outputTokens != null) && (
        <div className="flex gap-3">
          {inputTokens != null && <span>in: {inputTokens}</span>}
          {outputTokens != null && <span>out: {outputTokens}</span>}
        </div>
      )}
      {tool && <div>tool: {tool}</div>}
      {toolResult != null && (
        <pre className="text-gray-500 bg-gray-900 rounded p-1 overflow-x-auto max-h-16 overflow-y-auto text-[8px]">
          {typeof toolResult === "string" ? toolResult : JSON.stringify(toolResult, null, 2)}
        </pre>
      )}
      {!inputTokens && !outputTokens && !tool && !toolResult && Object.keys(attrs).length > 0 && (
        <pre className="text-gray-500 bg-gray-900 rounded p-1 max-h-16 overflow-auto text-[8px]">
          {JSON.stringify(attrs, null, 2)}
        </pre>
      )}
    </div>
  );
}

export function CompareView({ runA, runB }: CompareViewProps) {
  const { runs, setCompare, compareSelection } = useConsoleStore();

  if (!runA.trace || !runB.trace) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
        Both runs must have trace data to compare
      </div>
    );
  }

  const spansA = runA.trace.spans;
  const spansB = runB.trace.spans;
  const matched = matchSpans(spansA, spansB);
  const maxDuration = Math.max(
    ...spansA.map((s) => s.duration_ms ?? 0),
    ...spansB.map((s) => s.duration_ms ?? 0),
    1
  );

  const tokensInA = spansA.reduce((s, sp) => s + ((sp.attributes.input_tokens as number) ?? 0), 0);
  const tokensInB = spansB.reduce((s, sp) => s + ((sp.attributes.input_tokens as number) ?? 0), 0);
  const tokensOutA = spansA.reduce((s, sp) => s + ((sp.attributes.output_tokens as number) ?? 0), 0);
  const tokensOutB = spansB.reduce((s, sp) => s + ((sp.attributes.output_tokens as number) ?? 0), 0);

  function runLabel(run: RunRecord, idx: number) {
    return `#${idx} — ${run.query.slice(0, 20)}${run.query.length > 20 ? "…" : ""} (${(run.durationMs / 1000).toFixed(1)}s)`;
  }

  return (
    <div className="flex-1 flex flex-col bg-gray-950 min-w-0 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <GitCompareArrows size={14} className="text-gray-500" />
          <span className="text-[9px] uppercase tracking-[1.5px] text-gray-500 font-semibold">
            Compare
          </span>
          <div className="flex items-center gap-1.5 ml-1">
            <select
              className="bg-cyan-500/10 text-cyan-400 text-[10px] font-medium rounded px-1.5 py-0.5 border border-cyan-500/20 focus:outline-none focus:border-cyan-500/50"
              value={runA.id}
              onChange={(e) =>
                setCompare([e.target.value, compareSelection![1]])
              }
            >
              {runs.map((r, i) => (
                <option key={r.id} value={r.id}>
                  A: {runLabel(r, i + 1)}
                </option>
              ))}
            </select>
            <span className="text-gray-600 text-[10px]">vs</span>
            <select
              className="bg-orange-500/10 text-orange-400 text-[10px] font-medium rounded px-1.5 py-0.5 border border-orange-500/20 focus:outline-none focus:border-orange-500/50"
              value={runB.id}
              onChange={(e) =>
                setCompare([compareSelection![0], e.target.value])
              }
            >
              {runs.map((r, i) => (
                <option key={r.id} value={r.id}>
                  B: {runLabel(r, i + 1)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <button
          onClick={() => setCompare(null)}
          className="flex items-center gap-1 text-[10px] text-red-400 hover:text-red-300 transition-colors"
        >
          <X size={12} />
          Exit Compare
        </button>
      </div>

      {/* Summary stats */}
      <div className="px-4 py-3 border-b border-gray-800 flex gap-3 overflow-x-auto">
        <StatCard
          label="Duration"
          valueA={runA.durationMs}
          valueB={runB.durationMs}
          format={(v) => `${(v / 1000).toFixed(1)}s`}
        />
        <StatCard
          label="Tokens In"
          valueA={runA.usage?.tokens_in ?? tokensInA}
          valueB={runB.usage?.tokens_in ?? tokensInB}
          format={(v) => String(v)}
        />
        <StatCard
          label="Tokens Out"
          valueA={runA.usage?.tokens_out ?? tokensOutA}
          valueB={runB.usage?.tokens_out ?? tokensOutB}
          format={(v) => String(v)}
        />
        <StatCard
          label="Spans"
          valueA={spansA.length}
          valueB={spansB.length}
          format={(v) => String(v)}
        />
      </div>

      {/* Matched span list */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        <div className="text-[8px] uppercase tracking-wider text-gray-600 mb-2 font-semibold">
          Span-by-span comparison ({matched.length} spans)
        </div>
        {matched.map((row, i) => (
          <CompareSpanRow
            key={`${row.name}-${i}`}
            name={row.name}
            a={row.a}
            b={row.b}
            maxDuration={maxDuration}
          />
        ))}
      </div>
    </div>
  );
}
