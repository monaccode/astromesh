import { ArrowUp, ArrowDown } from "lucide-react";
import type { ChatMessage, RunRecord } from "../../types/console";
import { ToolUsageIndicator } from "./ToolUsageIndicator";

interface ChatBubbleProps {
  message: ChatMessage;
  run?: RunRecord;
}

export function ChatBubble({ message, run }: ChatBubbleProps) {
  const isUser = message.role === "user";
  const time = new Date(message.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  const totalTokens =
    run?.usage ? (run.usage.tokens_in ?? 0) + (run.usage.tokens_out ?? 0) : 0;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[80%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`px-3.5 py-2.5 text-sm leading-relaxed ${
            isUser
              ? "bg-blue-900/50 text-gray-100 rounded-2xl rounded-br-sm"
              : "bg-gray-800 text-gray-100 rounded-2xl rounded-bl-sm"
          }`}
        >
          {!isUser && run && <ToolUsageIndicator steps={run.steps} />}
          <span className="whitespace-pre-wrap">{message.content}</span>
        </div>
        <div
          className={`text-[10px] text-gray-600 mt-0.5 flex items-center gap-2 ${isUser ? "justify-end" : ""}`}
        >
          {time}
          {!isUser && run && (
            <>
              <span>{(run.durationMs / 1000).toFixed(1)}s</span>
              {totalTokens > 0 && (
                <span className="inline-flex items-center gap-1.5">
                  <span className="inline-flex items-center gap-0.5 text-cyan-400/60">
                    <ArrowUp size={8} /> {run.usage!.tokens_in}
                  </span>
                  <span className="inline-flex items-center gap-0.5 text-amber-400/60">
                    <ArrowDown size={8} /> {run.usage!.tokens_out}
                  </span>
                </span>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
