import { Eraser, RotateCcw } from "lucide-react";
import { useConsoleStore } from "../../stores/console";
import { Button } from "../ui/Button";
import { AgentSelector } from "./AgentSelector";
import { OverrideControls } from "./OverrideControls";

export function ConsoleLeftPanel() {
  const { selectedAgent, clearChat, resetSession } = useConsoleStore();

  return (
    <div className="w-[230px] flex-shrink-0 bg-gray-900 border-r border-gray-800 p-3.5 flex flex-col gap-3 overflow-y-auto">
      <AgentSelector />
      {selectedAgent && <OverrideControls />}
      <div className="flex-1" />
      <div className="flex flex-col gap-1.5">
        <Button variant="secondary" icon={Eraser} className="text-xs w-full" onClick={clearChat}>
          Clear Chat
        </Button>
        <Button variant="danger" icon={RotateCcw} className="text-xs w-full" onClick={resetSession}>
          Reset Session
        </Button>
      </div>
    </div>
  );
}
