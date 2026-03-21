import { Terminal } from "lucide-react";
import { useConsoleStore } from "../../stores/console";
import { ChatMessageList } from "./ChatMessageList";
import { ChatInput } from "./ChatInput";
import { RunSummaryBar } from "./RunSummaryBar";

export function ConsoleCenterPanel() {
  const { sessionId, error } = useConsoleStore();

  return (
    <div className="flex-1 flex flex-col bg-gray-950 min-w-0">
      <div className="px-4 py-2.5 border-b border-gray-800 flex justify-between items-center">
        <div className="flex items-center gap-1.5 text-[9px] uppercase tracking-[1.5px] text-gray-500 font-semibold">
          <Terminal size={12} />
          Playground
        </div>
        <div className="text-[10px] text-gray-600">
          Session: {sessionId.slice(0, 8)}
        </div>
      </div>

      {error && (
        <div className="mx-4 mt-2 px-3 py-2 bg-red-500/10 border border-red-500/30 rounded text-red-400 text-xs">
          {error}
        </div>
      )}

      <ChatMessageList />
      <RunSummaryBar />
      <ChatInput />
    </div>
  );
}
