import type { SpanTreeNode } from "../../utils/trace-tree";

interface SpanOverviewTabProps {
  node: SpanTreeNode;
  onSwitchTab: (tab: string) => void;
}

export function SpanOverviewTab({ node, onSwitchTab }: SpanOverviewTabProps) {
  const a = node.attributes;
  const hasMetrics = a.model || a.provider || a.latency_ms != null || a.cost != null;
  const hasTokens = a.input_tokens != null || a.output_tokens != null;
  const orchSteps = node.events.filter((e) => e.name === "orch_step");
  const hasResponse = typeof a.response === "string" && a.response.length > 0;
  const isError = node.status === "error";

  return (
    <div className="flex flex-col gap-3 p-3 text-[11px]">
      {/* Metrics grid */}
      {hasMetrics && (
        <div className="grid grid-cols-2 gap-2">
          {a.model && (
            <div className="bg-gray-800 rounded p-2">
              <div className="text-gray-500 text-[9px] uppercase mb-0.5">Model</div>
              <div className="text-amber-400">{a.model}</div>
            </div>
          )}
          {a.provider && (
            <div className="bg-gray-800 rounded p-2">
              <div className="text-gray-500 text-[9px] uppercase mb-0.5">Provider</div>
              <div className="text-amber-400">{a.provider}</div>
            </div>
          )}
          {a.latency_ms != null && (
            <div className="bg-gray-800 rounded p-2">
              <div className="text-gray-500 text-[9px] uppercase mb-0.5">Latency</div>
              <div className="text-orange-400">
                {a.latency_ms < 1000
                  ? `${Math.round(a.latency_ms)}ms`
                  : `${(a.latency_ms / 1000).toFixed(1)}s`}
              </div>
            </div>
          )}
          {a.cost != null && (
            <div className="bg-gray-800 rounded p-2">
              <div className="text-gray-500 text-[9px] uppercase mb-0.5">Cost</div>
              <div className="text-green-400">${a.cost.toFixed(4)}</div>
            </div>
          )}
        </div>
      )}

      {/* Token usage */}
      {hasTokens && (
        <div className="bg-gray-800 rounded p-2 flex gap-4">
          {a.input_tokens != null && (
            <div>
              <span className="text-cyan-400 font-semibold text-sm">{a.input_tokens}</span>
              <span className="text-gray-500 ml-1">input</span>
            </div>
          )}
          {a.output_tokens != null && (
            <div>
              <span className="text-amber-400 font-semibold text-sm">{a.output_tokens}</span>
              <span className="text-gray-500 ml-1">output</span>
            </div>
          )}
          {a.input_tokens != null && a.output_tokens != null && (
            <div>
              <span className="text-gray-200 font-semibold text-sm">
                {a.input_tokens + a.output_tokens}
              </span>
              <span className="text-gray-500 ml-1">total</span>
            </div>
          )}
        </div>
      )}

      {/* Orchestration steps */}
      {orchSteps.length > 0 && (
        <div className="bg-gray-800 rounded p-2">
          <div className="text-gray-500 text-[9px] uppercase mb-2">
            Orchestration — {String(orchSteps[0].attributes.pattern)} ({orchSteps.length} steps)
          </div>
          <div className="flex flex-col gap-2">
            {orchSteps.map((event, i) => {
              const ea = event.attributes;
              return (
                <div key={i} className="flex flex-col gap-1">
                  <div className="text-gray-500 text-[9px]">Step {Number(ea.iteration)}</div>
                  {ea.thought != null && (
                    <div className="border-l-2 border-purple-400 pl-2 bg-purple-400/5 rounded-r py-1">
                      <span className="text-purple-400 text-[9px] font-semibold">THOUGHT</span>
                      <div className="text-gray-300 text-[10px] mt-0.5">{String(ea.thought)}</div>
                    </div>
                  )}
                  {ea.action != null && (
                    <div className="border-l-2 border-orange-400 pl-2 bg-orange-400/5 rounded-r py-1">
                      <span className="text-orange-400 text-[9px] font-semibold">ACTION</span>
                      <div className="text-gray-300 text-[10px] mt-0.5">{String(ea.action)}</div>
                      {ea.action_input != null && (
                        <pre className="text-green-400 text-[9px] mt-0.5 overflow-x-auto">
                          {JSON.stringify(ea.action_input, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                  {ea.observation != null && (
                    <div className="border-l-2 border-blue-400 pl-2 bg-blue-400/5 rounded-r py-1">
                      <span className="text-blue-400 text-[9px] font-semibold">OBSERVATION</span>
                      <div className="text-gray-300 text-[10px] mt-0.5 break-all">
                        {String(ea.observation)}
                      </div>
                    </div>
                  )}
                  {ea.result != null && (
                    <div className="border-l-2 border-green-400 pl-2 bg-green-400/5 rounded-r py-1">
                      <span className="text-green-400 text-[9px] font-semibold">RESULT</span>
                      <div className="text-gray-300 text-[10px] mt-0.5">{String(ea.result)}</div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Response preview */}
      {hasResponse && (
        <div className="bg-gray-800 rounded p-2">
          <div className="text-gray-500 text-[9px] uppercase mb-0.5">Response Preview</div>
          <div className="text-gray-300 text-[10px] line-clamp-3">
            {a.response!.slice(0, 200)}
            {a.response!.length > 200 && "..."}
          </div>
          <button
            className="text-cyan-400 text-[9px] mt-1 hover:underline"
            onClick={() => onSwitchTab("output")}
          >
            View full response
          </button>
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="bg-red-500/10 border border-red-500/30 rounded p-2">
          <div className="text-red-400 text-[9px] uppercase mb-0.5">Error</div>
          <div className="text-red-300 text-[10px] font-mono">
            {(a.error_message as string) ?? "Unknown error"}
          </div>
        </div>
      )}

      {/* Tool info (for tool.call spans) */}
      {a.tool && (
        <div className="bg-gray-800 rounded p-2">
          <div className="text-gray-500 text-[9px] uppercase mb-0.5">Tool</div>
          <div className="text-orange-400">{a.tool}</div>
        </div>
      )}
    </div>
  );
}
