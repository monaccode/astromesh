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
          className={`text-[10px] text-gray-600 mt-0.5 ${isUser ? "text-right" : ""}`}
        >
          {time}
          {!isUser && run && (
            <span className="ml-2">
              {(run.durationMs / 1000).toFixed(1)}s
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
