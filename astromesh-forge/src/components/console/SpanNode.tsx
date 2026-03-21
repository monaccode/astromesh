import { useState } from "react";
import type { SpanTreeNode } from "../../utils/trace-tree";
import { getSpanColor, getSpanDotColor } from "../../utils/trace-tree";

interface SpanNodeProps {
  node: SpanTreeNode;
  rootDuration: number;
  depth?: number;
}

export function SpanNode({ node, rootDuration, depth = 0 }: SpanNodeProps) {
  const [expanded, setExpanded] = useState(false);
  const hasChildren = node.children.length > 0;
  const hasContent =
    Object.keys(node.attributes).length > 0 || node.events.length > 0;
  const isExpandable = hasChildren || hasContent;

  const duration = node.duration_ms ?? 0;
  const barWidth = rootDuration > 0 ? (duration / rootDuration) * 100 : 0;
  const isError = node.status === "error";

  return (
    <div style={{ marginLeft: depth > 0 ? 14 : 0 }}>
      <div
        className={`bg-gray-800 rounded px-2 py-1.5 border-l-[3px] ${
          isError ? "border-red-500" : getSpanColor(node.name)
        } ${isExpandable ? "cursor-pointer" : ""} mb-0.5`}
        onClick={() => isExpandable && setExpanded(!expanded)}
      >
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-1.5 min-w-0">
            {isExpandable && (
              <span
                className={`text-[8px] ${getSpanDotColor(node.name)}`}
              >
                {expanded ? "▾" : "▸"}
              </span>
            )}
            <span
              className={`text-[10px] truncate ${
                isError
                  ? "text-red-400"
                  : depth === 0
                    ? "text-gray-100 font-semibold"
                    : "text-gray-300"
              }`}
            >
              {node.name}
            </span>
            {node.status === "ok" && (
              <span className="bg-green-500/20 text-green-400 text-[8px] px-1 rounded">
                OK
              </span>
            )}
            {isError && (
              <span className="bg-red-500/20 text-red-400 text-[8px] px-1 rounded">
                ERR
              </span>
            )}
          </div>
          <span className="text-[10px] text-gray-500 font-mono flex-shrink-0 ml-2">
            {duration}ms
          </span>
        </div>

        {barWidth > 0 && (
          <div className="mt-1 bg-gray-900 rounded-sm h-[3px]">
            <div
              className={`h-full rounded-sm opacity-50 ${
                isError ? "bg-red-500" : "bg-cyan-500"
              }`}
              style={{ width: `${Math.max(barWidth, 1)}%` }}
            />
          </div>
        )}
      </div>

      {expanded && hasContent && (
        <div className="ml-3 mb-1 bg-gray-950 rounded p-2 text-[9px]">
          {renderAttributes(node)}
        </div>
      )}

      {expanded &&
        node.children.map((child) => (
          <SpanNode
            key={child.span_id}
            node={child}
            rootDuration={rootDuration}
            depth={depth + 1}
          />
        ))}
    </div>
  );
}

function renderAttributes(node: SpanTreeNode) {
  const attrs = node.attributes;
  const meta = attrs.metadata as Record<string, unknown> | undefined;

  const usage = meta?.usage as
    | { prompt_tokens?: number; completion_tokens?: number }
    | undefined;
  const model = meta?.model as string | undefined;
  const provider = meta?.provider as string | undefined;
  const toolArgs = (attrs.tool_args ?? meta?.args) as unknown;
  const toolResult = (attrs.tool_result ?? meta?.result) as unknown;
  const promptText = (attrs.prompt ?? meta?.prompt) as string | undefined;
  const responseText = (attrs.response ?? meta?.response) as
    | string
    | undefined;

  return (
    <div className="flex flex-col gap-1.5">
      {(usage || model || provider) && (
        <div className="flex gap-3 text-gray-400">
          {usage?.prompt_tokens != null && (
            <span>
              <span className="text-cyan-400">&#x2B06;</span>{" "}
              {usage.prompt_tokens} tokens
            </span>
          )}
          {usage?.completion_tokens != null && (
            <span>
              <span className="text-amber-400">&#x2B07;</span>{" "}
              {usage.completion_tokens} tokens
            </span>
          )}
          {model && <span>model: {model}</span>}
          {provider && <span>provider: {provider}</span>}
        </div>
      )}

      {promptText && (
        <div>
          <div className="text-gray-600 text-[8px] uppercase mb-0.5">
            Prompt
          </div>
          <pre className="text-gray-300 bg-gray-900 rounded p-1.5 overflow-x-auto max-h-24 overflow-y-auto whitespace-pre-wrap text-[9px]">
            {promptText}
          </pre>
        </div>
      )}

      {responseText && (
        <div>
          <div className="text-gray-600 text-[8px] uppercase mb-0.5">
            Response
          </div>
          <pre className="text-gray-300 bg-gray-900 rounded p-1.5 overflow-x-auto max-h-24 overflow-y-auto whitespace-pre-wrap text-[9px]">
            {responseText}
          </pre>
        </div>
      )}

      {toolArgs != null && (
        <div>
          <div className="text-gray-600 text-[8px] uppercase mb-0.5">
            Arguments
          </div>
          <pre className="text-gray-300 bg-gray-900 rounded p-1.5 overflow-x-auto max-h-16 overflow-y-auto text-[9px]">
            {typeof toolArgs === "string"
              ? toolArgs
              : JSON.stringify(toolArgs, null, 2)}
          </pre>
        </div>
      )}

      {toolResult != null && (
        <div>
          <div className="text-gray-600 text-[8px] uppercase mb-0.5">
            Result
          </div>
          <pre className="text-green-400 bg-gray-900 rounded p-1.5 overflow-x-auto max-h-16 overflow-y-auto text-[9px]">
            {typeof toolResult === "string"
              ? toolResult
              : JSON.stringify(toolResult, null, 2)}
          </pre>
        </div>
      )}

      {!usage &&
        !model &&
        !promptText &&
        !responseText &&
        !toolArgs &&
        !toolResult &&
        Object.keys(attrs).length > 0 && (
          <pre className="text-gray-400 bg-gray-900 rounded p-1.5 overflow-x-auto max-h-24 overflow-y-auto text-[9px]">
            {JSON.stringify(attrs, null, 2)}
          </pre>
        )}
    </div>
  );
}
