"use client";

import { useState } from "react";
import { useWizardStore } from "@/lib/store";
import { useAuthStore } from "@/lib/store";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { TestChat } from "@/components/chat/TestChat";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildYaml(config: ReturnType<typeof useWizardStore.getState>["config"]): string {
  const toolLines =
    config.tools.length > 0
      ? config.tools.map((t) => `    - id: ${t}`).join("\n")
      : "    []";

  const promptLines = config.systemPrompt
    ? config.systemPrompt
        .split("\n")
        .map((l, i) => (i === 0 ? l : `      ${l}`))
        .join("\n")
    : "# (empty)";

  return `apiVersion: astromesh/v1
kind: Agent
metadata:
  name: ${config.agentName || "<slug>"}
spec:
  identity:
    displayName: "${config.displayName || ""}"
    description: "${config.description || ""}"
    tone: ${config.tone}
  model:
    primary: ${config.model}
    provider: ${config.provider}
    routing: ${config.routingStrategy}${config.fallbackModel ? `\n    fallback: ${config.fallbackModel}` : ""}
  orchestration:
    pattern: ${config.channel || "single_pass"}
    maxIterations: ${config.maxIterations}
  prompts:
    system: |
      ${promptLines}
  tools:
${toolLines}
  memory:
    type: ${config.memoryType}
    strategy: ${config.memoryStrategy}
  guardrails:
    enabled: ${config.guardrailsEnabled}`;
}

// ---------------------------------------------------------------------------
// Code snippet builders
// ---------------------------------------------------------------------------

type SnippetTab = "curl" | "python" | "javascript";

function buildSnippets(
  orgSlug: string,
  agentName: string,
  baseUrl: string
): Record<SnippetTab, string> {
  const endpoint = `${baseUrl}/api/v1/orgs/${orgSlug}/agents/${agentName}/run`;

  return {
    curl: `curl -X POST "${endpoint}" \\
  -H "Authorization: Bearer <YOUR_API_KEY>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "query": "Hello!",
    "session_id": "optional-session-id"
  }'`,

    python: `import httpx

response = httpx.post(
    "${endpoint}",
    headers={"Authorization": "Bearer <YOUR_API_KEY>"},
    json={"query": "Hello!", "session_id": "optional-session-id"},
)
data = response.json()
print(data["response"])`,

    javascript: `const response = await fetch("${endpoint}", {
  method: "POST",
  headers: {
    "Authorization": "Bearer <YOUR_API_KEY>",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    query: "Hello!",
    session_id: "optional-session-id",
  }),
});

const { response: text } = await response.json();
console.log(text);`,
  };
}

// ---------------------------------------------------------------------------
// CopyButton
// ---------------------------------------------------------------------------

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard unavailable
    }
  }

  return (
    <button
      onClick={handleCopy}
      className={cn(
        "text-xs px-2 py-1 rounded transition-colors",
        copied
          ? "text-am-cyan bg-am-cyan/10"
          : "text-am-text-dim hover:text-am-text bg-am-surface/50"
      )}
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

// ---------------------------------------------------------------------------
// StepDeploy
// ---------------------------------------------------------------------------

type DeployState = "idle" | "deploying" | "success" | "error";

export function StepDeploy() {
  const config = useWizardStore((s) => s.config);
  const orgSlug = useAuthStore((s) => s.orgSlug) ?? "my-org";

  // YAML preview
  const [yamlOpen, setYamlOpen] = useState(false);
  const yaml = buildYaml(config);

  // Test chat
  const [chatOpen, setChatOpen] = useState(false);

  // Deploy state
  const [deployState, setDeployState] = useState<DeployState>("idle");
  const [deployError, setDeployError] = useState<string | null>(null);

  // Code snippets
  const [activeTab, setActiveTab] = useState<SnippetTab>("curl");
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
  const snippets = buildSnippets(orgSlug, config.agentName || "my-agent", baseUrl);
  const endpointUrl = `${baseUrl}/api/v1/orgs/${orgSlug}/agents/${
    config.agentName || "my-agent"
  }/run`;

  async function handleDeploy() {
    setDeployState("deploying");
    setDeployError(null);

    try {
      // Build the full agent config payload
      const payload = {
        apiVersion: "astromesh/v1",
        kind: "Agent",
        metadata: { name: config.agentName },
        spec: {
          identity: {
            displayName: config.displayName,
            description: config.description,
            tone: config.tone,
          },
          model: {
            primary: config.model,
            provider: config.provider,
            routing: config.routingStrategy,
            ...(config.fallbackModel && { fallback: config.fallbackModel }),
          },
          orchestration: {
            pattern: config.channel || "single_pass",
            maxIterations: config.maxIterations,
          },
          prompts: { system: config.systemPrompt },
          tools: config.tools.map((t) => ({ id: t })),
          memory: { type: config.memoryType, strategy: config.memoryStrategy },
          guardrails: { enabled: config.guardrailsEnabled },
        },
      };

      await api.createAgent(orgSlug, payload);
      await api.deployAgent(orgSlug, config.agentName);
      setDeployState("success");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Deploy failed";
      setDeployError(msg);
      setDeployState("error");
    }
  }

  const TABS: { id: SnippetTab; label: string }[] = [
    { id: "curl", label: "curl" },
    { id: "python", label: "Python" },
    { id: "javascript", label: "JavaScript" },
  ];

  return (
    <div className="space-y-8">
      {/* Heading */}
      <div>
        <h2 className="text-lg font-semibold text-am-text">
          Preview, Test & Deploy
        </h2>
        <p className="mt-1 text-sm text-am-text-dim">
          Review your configuration, test the agent, then go live.
        </p>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Section 1 — YAML Preview                                            */}
      {/* ------------------------------------------------------------------ */}
      <section>
        <button
          onClick={() => setYamlOpen((o) => !o)}
          className="flex w-full items-center justify-between rounded-xl border border-am-border bg-am-surface px-4 py-3 hover:border-am-border-hover transition-colors"
        >
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-am-text">
              YAML Preview
            </span>
            <span className="text-xs font-mono text-am-text-dim">
              agent.yaml
            </span>
          </div>
          <div className="flex items-center gap-2">
            <CopyButton text={yaml} />
            <span className="text-am-text-dim text-sm">
              {yamlOpen ? "▲" : "▼"}
            </span>
          </div>
        </button>

        {yamlOpen && (
          <div className="mt-2 rounded-xl border border-am-border bg-am-bg overflow-hidden">
            <pre className="p-4 text-xs font-mono text-am-text-dim leading-relaxed overflow-x-auto whitespace-pre max-h-[400px] overflow-y-auto">
              {yaml}
            </pre>
          </div>
        )}
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Section 2 — Test Chat                                               */}
      {/* ------------------------------------------------------------------ */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-am-text">Test Agent</p>
            <p className="text-xs text-am-text-dim">
              Send a test message before going live.
            </p>
          </div>
          {!chatOpen && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setChatOpen(true)}
            >
              Open Test Chat
            </Button>
          )}
        </div>

        {chatOpen && (
          <TestChat
            orgSlug={orgSlug}
            agentName={config.agentName || "my-agent"}
            onClose={() => setChatOpen(false)}
          />
        )}
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Section 3 — Deploy                                                  */}
      {/* ------------------------------------------------------------------ */}
      <section className="space-y-4">
        {deployState !== "success" && (
          <>
            <div className="rounded-xl border border-am-border bg-am-surface px-5 py-4 space-y-1">
              <p className="text-sm font-semibold text-am-text">
                Ready to deploy
              </p>
              <p className="text-xs text-am-text-dim leading-relaxed">
                Agent{" "}
                <span className="font-mono text-am-text">
                  {config.agentName || "your-agent"}
                </span>{" "}
                will be created with model{" "}
                <span className="font-mono text-am-text">{config.model}</span>{" "}
                and {config.tools.length} tool
                {config.tools.length !== 1 ? "s" : ""} enabled.
              </p>
            </div>

            {deployError && (
              <div className="rounded-md bg-am-red/10 border border-am-red/30 px-4 py-3 text-sm text-am-red">
                {deployError}
              </div>
            )}

            <Button
              variant="primary"
              loading={deployState === "deploying"}
              onClick={handleDeploy}
            >
              {deployState === "error" ? "Retry Deploy" : "Deploy Agent →"}
            </Button>
          </>
        )}

        {/* Success state */}
        {deployState === "success" && (
          <div className="space-y-6">
            {/* Success banner */}
            <div className="rounded-xl border border-am-cyan/40 bg-am-cyan-dim px-5 py-4 flex items-start gap-3">
              <span className="text-2xl">&#10003;</span>
              <div>
                <p className="text-sm font-semibold text-am-cyan">
                  Agent deployed!
                </p>
                <p className="mt-0.5 text-xs text-am-text-dim">
                  Your agent is live and ready to receive requests.
                </p>
              </div>
            </div>

            {/* API endpoint */}
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-am-text-dim uppercase tracking-wide">
                API Endpoint
              </p>
              <div className="flex items-center gap-2 rounded-md bg-am-bg border border-am-border px-3 py-2">
                <span className="flex-1 text-xs font-mono text-am-cyan break-all">
                  {endpointUrl}
                </span>
                <CopyButton text={endpointUrl} />
              </div>
            </div>

            {/* Code snippets */}
            <div className="space-y-2">
              <p className="text-xs font-medium text-am-text-dim uppercase tracking-wide">
                Code Examples
              </p>

              {/* Tab bar */}
              <div className="flex items-center gap-1 border-b border-am-border">
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={cn(
                      "px-3 py-1.5 text-xs font-medium border-b-2 -mb-px transition-colors",
                      activeTab === tab.id
                        ? "border-am-cyan text-am-cyan"
                        : "border-transparent text-am-text-dim hover:text-am-text"
                    )}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Code block */}
              <div className="relative rounded-xl border border-am-border bg-am-bg overflow-hidden">
                <div className="absolute top-2 right-2">
                  <CopyButton text={snippets[activeTab]} />
                </div>
                <pre className="p-4 pt-8 text-xs font-mono text-am-text-dim leading-relaxed overflow-x-auto whitespace-pre">
                  {snippets[activeTab]}
                </pre>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
