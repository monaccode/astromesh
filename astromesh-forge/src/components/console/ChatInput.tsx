import { useState, useCallback, type KeyboardEvent } from "react";
import { Send } from "lucide-react";
import { useConsoleStore } from "../../stores/console";
import { Tooltip } from "../ui/Tooltip";

export function ChatInput() {
  const { selectedAgent, running, sendMessage } = useConsoleStore();
  const [text, setText] = useState("");

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || running || !selectedAgent) return;
    sendMessage(trimmed);
    setText("");
  }, [text, running, selectedAgent, sendMessage]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const disabled = !selectedAgent || running;

  return (
    <div className="px-4 py-3 border-t border-gray-800 bg-gray-950 flex gap-2">
      <textarea
        className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3.5 py-2.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-cyan-500 resize-none"
        rows={1}
        placeholder={
          selectedAgent
            ? "Type a message to test your agent..."
            : "Select an agent first"
        }
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
      />
      <Tooltip text="Send message">
        <button
          className="bg-cyan-500 hover:bg-cyan-600 disabled:opacity-50 text-white font-bold px-4 py-2.5 rounded-lg transition-colors"
          onClick={handleSend}
          disabled={disabled || !text.trim()}
        >
          <Send size={18} />
        </button>
      </Tooltip>
    </div>
  );
}
