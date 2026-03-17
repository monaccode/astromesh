"use client";

import { useWizardStore } from "@/lib/store";
import { cn } from "@/lib/utils";

interface Tool {
  id: string;
  label: string;
  description: string;
  icon: string;
}

const AVAILABLE_TOOLS: Tool[] = [
  { id: "web_search", label: "Web Search", description: "Search the internet for up-to-date information.", icon: "🔍" },
  { id: "calculator", label: "Calculator", description: "Perform arithmetic and mathematical operations.", icon: "🧮" },
  { id: "datetime", label: "Date & Time", description: "Get current date, time, and timezone info.", icon: "🕐" },
  { id: "json_parser", label: "JSON Parser", description: "Parse, validate, and transform JSON data.", icon: "{ }" },
  { id: "http_request", label: "HTTP Request", description: "Call external APIs and fetch data.", icon: "🌐" },
  { id: "email_sender", label: "Email Sender", description: "Compose and send emails via SMTP.", icon: "✉️" },
  { id: "file_reader", label: "File Reader", description: "Read and extract text from uploaded files.", icon: "📄" },
  { id: "text_summarizer", label: "Text Summarizer", description: "Condense long text into key points.", icon: "📝" },
  { id: "translator", label: "Translator", description: "Translate content between 100+ languages.", icon: "🌍" },
  { id: "code_executor", label: "Code Executor", description: "Run Python snippets in a sandboxed environment.", icon: "💻" },
];

const COMING_SOON_TOOLS: Tool[] = [
  { id: "google_sheets", label: "Google Sheets", description: "Read and write spreadsheet data.", icon: "📊" },
  { id: "calendar", label: "Calendar", description: "Manage events and check availability.", icon: "📅" },
  { id: "drive", label: "Google Drive", description: "Access files and folders.", icon: "📁" },
  { id: "slack", label: "Slack", description: "Send messages and read channels.", icon: "💬" },
  { id: "whatsapp", label: "WhatsApp", description: "Send and receive WhatsApp messages.", icon: "📱" },
  { id: "notion", label: "Notion", description: "Read and write Notion pages.", icon: "📓" },
  { id: "hubspot", label: "HubSpot", description: "Access CRM contacts and deals.", icon: "🏢" },
  { id: "stripe", label: "Stripe", description: "Query payments and subscriptions.", icon: "💳" },
  { id: "sql_query", label: "SQL Query", description: "Run queries against a connected database.", icon: "🗄️" },
  { id: "rag_pipeline", label: "RAG Pipeline", description: "Search your knowledge base with embeddings.", icon: "🧠" },
  { id: "image_generator", label: "Image Generator", description: "Generate images from text prompts.", icon: "🖼️" },
  { id: "voice_transcriber", label: "Voice Transcriber", description: "Transcribe audio to text.", icon: "🎙️" },
];

export function StepTools() {
  const config = useWizardStore((s) => s.config);
  const updateConfig = useWizardStore((s) => s.updateConfig);

  function toggleTool(id: string) {
    const current = config.tools;
    const next = current.includes(id)
      ? current.filter((t) => t !== id)
      : [...current, id];
    updateConfig({ tools: next });
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-lg font-semibold text-am-text">Tool Catalog</h2>
        <p className="mt-1 text-sm text-am-text-dim">
          Select which tools your agent can use. Each tool is sandboxed and
          audited.
        </p>
      </div>

      {/* Available tools */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-am-text-dim uppercase tracking-wide">
            Available
          </span>
          <span className="rounded-full bg-am-green/10 border border-am-green/20 px-2 py-0.5 text-xs text-am-green">
            {config.tools.length} selected
          </span>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {AVAILABLE_TOOLS.map((tool) => {
            const enabled = config.tools.includes(tool.id);
            return (
              <button
                key={tool.id}
                onClick={() => toggleTool(tool.id)}
                className={cn(
                  "flex items-center gap-3 rounded-xl border p-3 text-left transition-all",
                  "hover:border-am-border-hover",
                  enabled
                    ? "border-am-cyan bg-am-cyan-dim shadow-[0_0_12px_rgba(0,212,255,0.15)]"
                    : "border-am-border bg-am-surface"
                )}
              >
                {/* Toggle indicator */}
                <div
                  className={cn(
                    "flex h-5 w-9 flex-shrink-0 items-center rounded-full border transition-all",
                    enabled
                      ? "bg-am-cyan border-am-cyan"
                      : "bg-am-bg border-am-border"
                  )}
                >
                  <span
                    className={cn(
                      "ml-0.5 h-4 w-4 rounded-full bg-am-bg transition-transform",
                      enabled && "translate-x-4"
                    )}
                  />
                </div>

                <span className="text-lg leading-none flex-shrink-0">{tool.icon}</span>

                <div className="min-w-0 flex-1">
                  <p
                    className={cn(
                      "text-sm font-medium",
                      enabled ? "text-am-cyan" : "text-am-text"
                    )}
                  >
                    {tool.label}
                  </p>
                  <p className="text-xs text-am-text-dim truncate">{tool.description}</p>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Coming soon */}
      <div className="space-y-3">
        <span className="text-xs font-medium text-am-text-dim uppercase tracking-wide">
          Coming Soon
        </span>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {COMING_SOON_TOOLS.map((tool) => (
            <div
              key={tool.id}
              className="flex items-center gap-3 rounded-xl border border-am-border/50 bg-am-surface/50 p-3 opacity-50 cursor-not-allowed"
            >
              <span className="text-lg leading-none flex-shrink-0 grayscale">{tool.icon}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-am-text-dim">{tool.label}</p>
                  <span className="rounded-full bg-white/5 border border-white/10 px-1.5 py-0.5 text-xs text-am-text-dim/50">
                    Coming Soon
                  </span>
                </div>
                <p className="text-xs text-am-text-dim/60 truncate">{tool.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
