import { useEffect, useRef } from "react";
import { useConsoleStore } from "../../stores/console";
import { ChatBubble } from "./ChatBubble";

export function ChatMessageList() {
  const { messages, runs, running } = useConsoleStore();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, running]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-3">
      {messages.length === 0 && !running && (
        <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
          Select an agent and send a message to start testing
        </div>
      )}
      {messages.map((msg) => {
        const run = msg.runId
          ? runs.find((r) => r.id === msg.runId)
          : undefined;
        return <ChatBubble key={msg.id} message={msg} run={run} />;
      })}
      {running && (
        <div className="flex justify-start">
          <div className="bg-gray-800 text-gray-500 px-3.5 py-2.5 rounded-2xl rounded-bl-sm text-sm flex items-center gap-2">
            <span className="flex gap-0.5">
              <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse" />
              <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse [animation-delay:200ms]" />
              <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse [animation-delay:400ms]" />
            </span>
            Running...
          </div>
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
