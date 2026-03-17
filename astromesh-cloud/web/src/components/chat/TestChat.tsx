"use client";

import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

interface TestChatProps {
  orgSlug: string;
  agentName: string;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// TestChat
// ---------------------------------------------------------------------------

export function TestChat({ orgSlug, agentName, onClose }: TestChatProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: `Hi! I'm ${agentName}. Send me a message to test how I respond.`,
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setError(null);
    setLoading(true);

    try {
      const res = await api.testAgent(orgSlug, agentName);
      const assistantMsg: Message = {
        id: `a-${Date.now()}`,
        role: "assistant",
        content: res.response ?? "(no response)",
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Request failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex flex-col rounded-xl border border-am-cyan/30 bg-am-bg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-am-border px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-am-cyan animate-pulse" />
          <span className="text-sm font-semibold text-am-text">
            Test Chat —{" "}
            <span className="font-mono text-am-cyan">{agentName}</span>
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-am-text-dim hover:text-am-text transition-colors text-sm"
          aria-label="Close test chat"
        >
          ✕
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-[240px] max-h-[360px]">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn(
              "flex",
              msg.role === "user" ? "justify-end" : "justify-start"
            )}
          >
            <div
              className={cn(
                "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
                msg.role === "user"
                  ? "bg-am-cyan text-am-bg font-medium rounded-br-sm"
                  : "bg-am-surface text-am-text border border-am-border rounded-bl-sm"
              )}
            >
              {msg.content}
            </div>
          </div>
        ))}

        {/* Loading bubble */}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-am-surface border border-am-border rounded-2xl rounded-bl-sm px-4 py-3">
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-am-text-dim animate-bounce [animation-delay:0ms]" />
                <span className="h-1.5 w-1.5 rounded-full bg-am-text-dim animate-bounce [animation-delay:150ms]" />
                <span className="h-1.5 w-1.5 rounded-full bg-am-text-dim animate-bounce [animation-delay:300ms]" />
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Error */}
      {error && (
        <div className="mx-4 mb-2 rounded-md bg-am-red/10 border border-am-red/30 px-3 py-2 text-xs text-am-red">
          {error}
        </div>
      )}

      {/* Input */}
      <div className="border-t border-am-border px-4 py-3 flex items-center gap-2">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          placeholder="Type a message..."
          className={cn(
            "flex-1 rounded-md bg-am-surface border border-am-border px-3 py-2 text-sm text-am-text",
            "placeholder:text-am-text-dim focus:outline-none focus:ring-2 focus:ring-am-cyan focus:border-transparent",
            "disabled:opacity-50 transition-all"
          )}
        />
        <Button
          variant="primary"
          size="sm"
          onClick={handleSend}
          disabled={!input.trim() || loading}
          loading={loading}
        >
          Send
        </Button>
      </div>
    </div>
  );
}
