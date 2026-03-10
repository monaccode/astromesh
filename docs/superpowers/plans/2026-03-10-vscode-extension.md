# VS Code Extension Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a VS Code extension that wraps the Astromesh CLI, providing YAML IntelliSense, workflow visualization, traces/metrics panels, agent execution, copilot chat, and diagnostics — with zero business logic in the extension itself.

**Architecture:** The extension is a thin visual layer over the existing `astromeshctl` CLI. All commands spawn CLI processes; webview panels fetch from the Astromesh REST API. JSON Schemas provide YAML IntelliSense via the built-in YAML extension.

**Tech Stack:** TypeScript, VS Code Extension API, @vscode/test-electron (testing), esbuild (bundling), JSON Schema (YAML validation)

---

## File Structure

```
vscode-extension/
├── package.json              # Extension manifest (contributes, activationEvents)
├── tsconfig.json             # TypeScript config
├── esbuild.js                # Build script
├── .vscodeignore             # Files excluded from VSIX
├── README.md                 # Marketplace README
├── CHANGELOG.md              # Extension changelog
├── media/
│   └── icon.png              # Extension icon
├── schemas/
│   ├── agent.schema.json     # JSON Schema for *.agent.yaml
│   └── workflow.schema.json  # JSON Schema for *.workflow.yaml
├── src/
│   ├── extension.ts          # activate/deactivate entry point
│   ├── cli.ts                # CLI wrapper (spawn astromeshctl commands, parse output)
│   ├── commands/
│   │   ├── runAgent.ts       # Run agent command (play button)
│   │   ├── runWorkflow.ts    # Run workflow command
│   │   ├── diagnostics.ts    # astromesh doctor wrapper
│   │   └── copilot.ts        # Copilot chat panel
│   ├── views/
│   │   ├── tracesProvider.ts # TreeDataProvider for traces sidebar
│   │   ├── metricsPanel.ts   # Webview panel for metrics dashboard
│   │   └── workflowPanel.ts  # Webview panel for workflow DAG visualizer
│   └── statusBar.ts          # Status bar item (daemon status)
├── webview/
│   ├── metrics.html          # Metrics dashboard HTML template
│   ├── workflow.html         # Workflow visualizer HTML template
│   └── copilot.html          # Copilot chat HTML template
└── test/
    ├── runTest.ts             # Test runner entry point
    └── suite/
        ├── cli.test.ts        # CLI wrapper unit tests
        ├── extension.test.ts  # Activation/command registration tests
        ├── traces.test.ts     # TreeDataProvider tests
        └── schemas.test.ts    # Schema validation tests
```

---

## Chunk 1: Extension Scaffold + CLI Wrapper

### Task 1: Initialize Extension Project

**Files:**
- Create: `vscode-extension/package.json`
- Create: `vscode-extension/tsconfig.json`
- Create: `vscode-extension/esbuild.js`
- Create: `vscode-extension/.vscodeignore`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "astromesh",
  "displayName": "Astromesh",
  "description": "AI Agent Runtime Platform — orchestrate, debug, and monitor agents from VS Code",
  "version": "0.1.0",
  "publisher": "monaccode",
  "license": "Apache-2.0",
  "engines": { "vscode": "^1.85.0" },
  "categories": ["Programming Languages", "Debuggers", "Machine Learning"],
  "keywords": ["ai", "agents", "llm", "orchestration", "astromesh"],
  "activationEvents": [
    "workspaceContains:**/*.agent.yaml",
    "workspaceContains:**/*.workflow.yaml"
  ],
  "main": "./dist/extension.js",
  "contributes": {
    "commands": [
      { "command": "astromesh.runAgent", "title": "Astromesh: Run Agent", "icon": "$(play)" },
      { "command": "astromesh.runWorkflow", "title": "Astromesh: Run Workflow", "icon": "$(play)" },
      { "command": "astromesh.doctor", "title": "Astromesh: Diagnostics" },
      { "command": "astromesh.copilot", "title": "Astromesh: Ask Copilot" },
      { "command": "astromesh.showMetrics", "title": "Astromesh: Metrics Dashboard" },
      { "command": "astromesh.showWorkflow", "title": "Astromesh: Visualize Workflow" },
      { "command": "astromesh.refreshTraces", "title": "Astromesh: Refresh Traces", "icon": "$(refresh)" }
    ],
    "viewsContainers": {
      "activitybar": [
        { "id": "astromesh", "title": "Astromesh", "icon": "$(hubot)" }
      ]
    },
    "views": {
      "astromesh": [
        { "id": "astromesh.traces", "name": "Traces" }
      ]
    },
    "menus": {
      "editor/title": [
        { "command": "astromesh.runAgent", "when": "resourceFilename =~ /\\.agent\\.yaml$/", "group": "navigation" },
        { "command": "astromesh.showWorkflow", "when": "resourceFilename =~ /\\.workflow\\.yaml$/", "group": "navigation" }
      ]
    },
    "yamlValidation": [
      { "fileMatch": "*.agent.yaml", "url": "./schemas/agent.schema.json" },
      { "fileMatch": "*.workflow.yaml", "url": "./schemas/workflow.schema.json" }
    ],
    "configuration": {
      "title": "Astromesh",
      "properties": {
        "astromesh.cliPath": {
          "type": "string",
          "default": "astromeshctl",
          "description": "Path to astromeshctl binary"
        },
        "astromesh.daemonUrl": {
          "type": "string",
          "default": "http://localhost:8000",
          "description": "Astromesh daemon URL"
        },
        "astromesh.traces.autoRefresh": {
          "type": "boolean",
          "default": true,
          "description": "Auto-refresh traces panel"
        },
        "astromesh.traces.refreshInterval": {
          "type": "number",
          "default": 10,
          "description": "Traces refresh interval in seconds"
        }
      }
    }
  },
  "scripts": {
    "build": "node esbuild.js",
    "watch": "node esbuild.js --watch",
    "test": "node ./dist/test/runTest.js",
    "package": "vsce package",
    "lint": "eslint src/"
  },
  "devDependencies": {
    "@types/vscode": "^1.85.0",
    "@types/mocha": "^10.0.0",
    "@types/node": "^20.0.0",
    "@vscode/test-electron": "^2.3.0",
    "@vscode/vsce": "^2.22.0",
    "esbuild": "^0.19.0",
    "mocha": "^10.2.0",
    "typescript": "^5.3.0"
  }
}
```

- [ ] **Step 2: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "module": "commonjs",
    "target": "ES2022",
    "outDir": "dist",
    "rootDir": ".",
    "lib": ["ES2022"],
    "sourceMap": true,
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true
  },
  "include": ["src/**/*", "test/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

- [ ] **Step 3: Create esbuild.js**

```javascript
const esbuild = require("esbuild");
const isWatch = process.argv.includes("--watch");

const buildOptions = {
  entryPoints: ["src/extension.ts"],
  bundle: true,
  outfile: "dist/extension.js",
  external: ["vscode"],
  format: "cjs",
  platform: "node",
  target: "node18",
  sourcemap: true,
};

if (isWatch) {
  esbuild.context(buildOptions).then((ctx) => ctx.watch());
} else {
  esbuild.build(buildOptions);
}
```

- [ ] **Step 4: Create .vscodeignore**

```
src/**
test/**
node_modules/**
.vscode/**
tsconfig.json
esbuild.js
*.map
```

- [ ] **Step 5: Install dependencies and verify build**

```bash
cd vscode-extension && npm install && npm run build
```
Expected: `dist/extension.js` created with no errors.

- [ ] **Step 6: Commit**

```bash
git add vscode-extension/package.json vscode-extension/tsconfig.json vscode-extension/esbuild.js vscode-extension/.vscodeignore
git commit -m "feat(vscode): scaffold extension project with manifest and build"
```

---

### Task 2: CLI Wrapper Utility

**Files:**
- Create: `vscode-extension/src/cli.ts`
- Create: `vscode-extension/test/suite/cli.test.ts`

- [ ] **Step 1: Write the CLI wrapper tests**

```typescript
// test/suite/cli.test.ts
import * as assert from "assert";
import { AstromeshCli, CliResult } from "../../src/cli";

suite("AstromeshCli", () => {
  test("parseJsonOutput handles valid JSON", () => {
    const cli = new AstromeshCli("astromeshctl");
    const result = cli.parseJsonOutput('{"version":"0.13.0"}');
    assert.deepStrictEqual(result, { version: "0.13.0" });
  });

  test("parseJsonOutput returns null for invalid JSON", () => {
    const cli = new AstromeshCli("astromeshctl");
    const result = cli.parseJsonOutput("not json");
    assert.strictEqual(result, null);
  });

  test("buildArgs constructs correct argument list", () => {
    const cli = new AstromeshCli("astromeshctl");
    const args = cli.buildArgs("run", ["my-agent", "hello"], { json: true, timeout: "30" });
    assert.deepStrictEqual(args, ["run", "my-agent", "hello", "--json", "--timeout", "30"]);
  });

  test("buildArgs omits flags with false values", () => {
    const cli = new AstromeshCli("astromeshctl");
    const args = cli.buildArgs("doctor", [], { json: false });
    assert.deepStrictEqual(args, ["doctor"]);
  });
});
```

- [ ] **Step 2: Implement CLI wrapper**

```typescript
// src/cli.ts
import { spawn } from "child_process";

export interface CliResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

export class AstromeshCli {
  constructor(private readonly cliPath: string) {}

  parseJsonOutput(output: string): unknown | null {
    try {
      return JSON.parse(output);
    } catch {
      return null;
    }
  }

  buildArgs(
    command: string,
    positional: string[],
    flags: Record<string, string | boolean> = {}
  ): string[] {
    const args = [command, ...positional];
    for (const [key, value] of Object.entries(flags)) {
      if (value === false) continue;
      args.push(`--${key}`);
      if (typeof value === "string") {
        args.push(value);
      }
    }
    return args;
  }

  exec(
    command: string,
    positional: string[] = [],
    flags: Record<string, string | boolean> = {}
  ): Promise<CliResult> {
    const args = this.buildArgs(command, positional, flags);
    return new Promise((resolve) => {
      const proc = spawn(this.cliPath, args, { shell: true });
      let stdout = "";
      let stderr = "";
      proc.stdout.on("data", (data) => (stdout += data.toString()));
      proc.stderr.on("data", (data) => (stderr += data.toString()));
      proc.on("close", (code) => {
        resolve({ stdout, stderr, exitCode: code ?? 1 });
      });
      proc.on("error", () => {
        resolve({ stdout, stderr, exitCode: 1 });
      });
    });
  }

  async execJson(
    command: string,
    positional: string[] = [],
    flags: Record<string, string | boolean> = {}
  ): Promise<{ data: unknown | null; error: string | null }> {
    const result = await this.exec(command, positional, { ...flags, json: true });
    if (result.exitCode !== 0) {
      return { data: null, error: result.stderr || `Exit code ${result.exitCode}` };
    }
    const data = this.parseJsonOutput(result.stdout);
    return { data, error: data === null ? "Failed to parse JSON output" : null };
  }
}
```

- [ ] **Step 3: Build and run tests**

```bash
cd vscode-extension && npm run build && npx mocha dist/test/suite/cli.test.js
```
Expected: 4 tests passing.

- [ ] **Step 4: Commit**

```bash
git add vscode-extension/src/cli.ts vscode-extension/test/suite/cli.test.ts
git commit -m "feat(vscode): add CLI wrapper with JSON parsing and arg builder"
```

---

### Task 3: Extension Entry Point + Status Bar

**Files:**
- Create: `vscode-extension/src/extension.ts`
- Create: `vscode-extension/src/statusBar.ts`

- [ ] **Step 1: Implement status bar**

```typescript
// src/statusBar.ts
import * as vscode from "vscode";
import { AstromeshCli } from "./cli";

export class StatusBarManager {
  private readonly item: vscode.StatusBarItem;
  private timer: ReturnType<typeof setInterval> | undefined;

  constructor(private readonly cli: AstromeshCli) {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
    this.item.command = "astromesh.doctor";
    this.item.text = "$(hubot) Astromesh";
    this.item.tooltip = "Click to run diagnostics";
    this.item.show();
  }

  async refresh(): Promise<void> {
    const { data, error } = await this.cli.execJson("status");
    if (error || !data) {
      this.item.text = "$(hubot) Astromesh $(circle-slash)";
      this.item.tooltip = "Daemon not reachable";
      return;
    }
    const status = data as Record<string, unknown>;
    const agents = status.agents_loaded ?? 0;
    this.item.text = `$(hubot) Astromesh $(check) ${agents} agents`;
    this.item.tooltip = `v${status.version} | ${status.mode} | uptime: ${Math.round(Number(status.uptime_seconds ?? 0))}s`;
  }

  startAutoRefresh(intervalSec: number): void {
    this.refresh();
    this.timer = setInterval(() => this.refresh(), intervalSec * 1000);
  }

  dispose(): void {
    if (this.timer) clearInterval(this.timer);
    this.item.dispose();
  }
}
```

- [ ] **Step 2: Implement extension entry point**

```typescript
// src/extension.ts
import * as vscode from "vscode";
import { AstromeshCli } from "./cli";
import { StatusBarManager } from "./statusBar";

let statusBar: StatusBarManager | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const config = vscode.workspace.getConfiguration("astromesh");
  const cliPath = config.get<string>("cliPath", "astromeshctl");
  const cli = new AstromeshCli(cliPath);

  // Status bar
  statusBar = new StatusBarManager(cli);
  statusBar.startAutoRefresh(30);
  context.subscriptions.push({ dispose: () => statusBar?.dispose() });

  // Register commands (stubs — implemented in later tasks)
  context.subscriptions.push(
    vscode.commands.registerCommand("astromesh.runAgent", () =>
      vscode.window.showInformationMessage("Run Agent: coming soon")
    ),
    vscode.commands.registerCommand("astromesh.runWorkflow", () =>
      vscode.window.showInformationMessage("Run Workflow: coming soon")
    ),
    vscode.commands.registerCommand("astromesh.doctor", () =>
      vscode.window.showInformationMessage("Diagnostics: coming soon")
    ),
    vscode.commands.registerCommand("astromesh.copilot", () =>
      vscode.window.showInformationMessage("Copilot: coming soon")
    ),
    vscode.commands.registerCommand("astromesh.showMetrics", () =>
      vscode.window.showInformationMessage("Metrics: coming soon")
    ),
    vscode.commands.registerCommand("astromesh.showWorkflow", () =>
      vscode.window.showInformationMessage("Workflow: coming soon")
    ),
    vscode.commands.registerCommand("astromesh.refreshTraces", () =>
      vscode.window.showInformationMessage("Refresh Traces: coming soon")
    )
  );
}

export function deactivate(): void {
  statusBar?.dispose();
}
```

- [ ] **Step 3: Build and verify**

```bash
cd vscode-extension && npm run build
```
Expected: `dist/extension.js` builds with no errors.

- [ ] **Step 4: Commit**

```bash
git add vscode-extension/src/extension.ts vscode-extension/src/statusBar.ts
git commit -m "feat(vscode): add extension entry point with status bar and command stubs"
```

---

## Chunk 2: YAML IntelliSense

### Task 4: Agent YAML JSON Schema

**Files:**
- Create: `vscode-extension/schemas/agent.schema.json`

- [ ] **Step 1: Write agent schema**

The schema must match the `astromesh/v1 Agent` YAML structure used in `config/agents/*.agent.yaml`. Reference: `astromesh/runtime/engine.py` agent loading and `docs-site/src/content/docs/configuration/agent-yaml.md`.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Astromesh Agent",
  "description": "Agent definition for Astromesh runtime (astromesh/v1 Agent)",
  "type": "object",
  "required": ["apiVersion", "kind", "metadata", "spec"],
  "properties": {
    "apiVersion": { "type": "string", "const": "astromesh/v1" },
    "kind": { "type": "string", "const": "Agent" },
    "metadata": {
      "type": "object",
      "required": ["name"],
      "properties": {
        "name": { "type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$", "description": "Unique agent identifier" },
        "version": { "type": "string", "default": "1.0.0" },
        "namespace": { "type": "string", "default": "default" }
      }
    },
    "spec": {
      "type": "object",
      "properties": {
        "identity": {
          "type": "object",
          "properties": {
            "display_name": { "type": "string" },
            "description": { "type": "string" }
          }
        },
        "model": {
          "type": "object",
          "properties": {
            "primary": { "$ref": "#/$defs/modelConfig" },
            "fallback": { "$ref": "#/$defs/modelConfig" },
            "routing": {
              "type": "object",
              "properties": {
                "strategy": {
                  "type": "string",
                  "enum": ["cost_optimized", "latency_optimized", "quality_first", "round_robin", "capability_match"]
                }
              }
            }
          }
        },
        "prompts": {
          "type": "object",
          "properties": {
            "system": { "type": "string", "description": "System prompt (supports Jinja2)" }
          }
        },
        "orchestration": {
          "type": "object",
          "properties": {
            "pattern": {
              "type": "string",
              "enum": ["react", "plan_and_execute", "pipeline", "parallel_fan_out", "supervisor", "swarm"]
            },
            "max_iterations": { "type": "integer", "minimum": 1, "default": 5 },
            "timeout_seconds": { "type": "integer", "minimum": 1 }
          }
        },
        "tools": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "type"],
            "properties": {
              "name": { "type": "string" },
              "type": {
                "type": "string",
                "enum": ["builtin", "internal", "mcp_stdio", "mcp_sse", "mcp_http", "webhook", "rag", "agent"]
              },
              "agent": { "type": "string", "description": "Agent name (when type: agent)" },
              "context_transform": { "type": "string", "description": "Jinja2 template for reshaping data" },
              "config": { "type": "object" }
            }
          }
        },
        "memory": {
          "type": "object",
          "properties": {
            "conversational": {
              "type": "object",
              "properties": {
                "backend": { "type": "string", "enum": ["redis", "postgres", "sqlite", "in_memory"] },
                "strategy": { "type": "string", "enum": ["sliding_window", "summary", "token_budget"] },
                "max_messages": { "type": "integer" }
              }
            },
            "semantic": {
              "type": "object",
              "properties": {
                "backend": { "type": "string", "enum": ["chromadb", "qdrant", "faiss", "pgvector"] }
              }
            }
          }
        },
        "guardrails": {
          "type": "object",
          "properties": {
            "input": { "type": "array", "items": { "type": "object" } },
            "output": { "type": "array", "items": { "type": "object" } }
          }
        },
        "observability": {
          "type": "object",
          "properties": {
            "tracing": { "type": "boolean", "default": true },
            "metrics": { "type": "boolean", "default": true },
            "collector": { "type": "string", "enum": ["stdout", "otlp", "internal"] },
            "sample_rate": { "type": "number", "minimum": 0, "maximum": 1 }
          }
        }
      }
    }
  },
  "$defs": {
    "modelConfig": {
      "type": "object",
      "required": ["provider", "model"],
      "properties": {
        "provider": { "type": "string", "enum": ["ollama", "openai", "vllm", "llamacpp", "huggingface", "onnx"] },
        "model": { "type": "string" },
        "endpoint": { "type": "string", "format": "uri" },
        "temperature": { "type": "number", "minimum": 0, "maximum": 2 },
        "max_tokens": { "type": "integer", "minimum": 1 }
      }
    }
  }
}
```

- [ ] **Step 2: Verify schema is valid JSON**

```bash
cd vscode-extension && node -e "JSON.parse(require('fs').readFileSync('schemas/agent.schema.json','utf8')); console.log('Valid')"
```
Expected: `Valid`

- [ ] **Step 3: Commit**

```bash
git add vscode-extension/schemas/agent.schema.json
git commit -m "feat(vscode): add JSON Schema for agent YAML IntelliSense"
```

---

### Task 5: Workflow YAML JSON Schema

**Files:**
- Create: `vscode-extension/schemas/workflow.schema.json`

- [ ] **Step 1: Write workflow schema**

Based on `astromesh/workflow/models.py` (StepSpec, WorkflowSpec, RetryConfig) and `config/workflows/example.workflow.yaml`.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Astromesh Workflow",
  "description": "Workflow definition for Astromesh runtime (astromesh/v1 Workflow)",
  "type": "object",
  "required": ["apiVersion", "kind", "metadata", "spec"],
  "properties": {
    "apiVersion": { "type": "string", "const": "astromesh/v1" },
    "kind": { "type": "string", "const": "Workflow" },
    "metadata": {
      "type": "object",
      "required": ["name"],
      "properties": {
        "name": { "type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$" },
        "version": { "type": "string" },
        "namespace": { "type": "string" },
        "description": { "type": "string" }
      }
    },
    "spec": {
      "type": "object",
      "required": ["steps"],
      "properties": {
        "trigger": {
          "type": "string",
          "enum": ["api", "schedule", "webhook", "event"],
          "default": "api"
        },
        "timeout_seconds": { "type": "integer", "minimum": 1, "default": 300 },
        "steps": {
          "type": "array",
          "minItems": 1,
          "items": { "$ref": "#/$defs/step" }
        },
        "observability": {
          "type": "object",
          "properties": {
            "collector": { "type": "string", "enum": ["stdout", "otlp", "internal"] }
          }
        }
      }
    }
  },
  "$defs": {
    "step": {
      "type": "object",
      "required": ["name"],
      "properties": {
        "name": { "type": "string" },
        "agent": { "type": "string", "description": "Agent to invoke (mutually exclusive with tool/switch)" },
        "tool": { "type": "string", "description": "Tool to invoke (mutually exclusive with agent/switch)" },
        "switch": {
          "type": "array",
          "description": "Conditional branching (mutually exclusive with agent/tool)",
          "items": {
            "type": "object",
            "properties": {
              "when": { "type": "string", "description": "Jinja2 condition" },
              "default": { "type": "boolean" },
              "goto": { "type": "string", "description": "Target step name" }
            }
          }
        },
        "input": { "type": "string", "description": "Jinja2 template for step input" },
        "arguments": { "type": "object", "description": "Arguments for tool steps" },
        "context_transform": { "type": "string", "description": "Jinja2 template for reshaping data" },
        "retry": {
          "type": "object",
          "properties": {
            "max_attempts": { "type": "integer", "minimum": 1, "default": 1 },
            "backoff": { "type": "string", "enum": ["fixed", "exponential"], "default": "fixed" },
            "initial_delay_seconds": { "type": "number", "default": 1.0 }
          }
        },
        "timeout_seconds": { "type": "integer", "minimum": 1 },
        "on_error": { "type": "string", "description": "Step name to goto on error, or 'fail' to abort" }
      }
    }
  }
}
```

- [ ] **Step 2: Verify schema is valid JSON**

```bash
cd vscode-extension && node -e "JSON.parse(require('fs').readFileSync('schemas/workflow.schema.json','utf8')); console.log('Valid')"
```
Expected: `Valid`

- [ ] **Step 3: Commit**

```bash
git add vscode-extension/schemas/workflow.schema.json
git commit -m "feat(vscode): add JSON Schema for workflow YAML IntelliSense"
```

---

## Chunk 3: Agent Execution + Diagnostics

### Task 6: Run Agent Command

**Files:**
- Create: `vscode-extension/src/commands/runAgent.ts`
- Modify: `vscode-extension/src/extension.ts`

- [ ] **Step 1: Implement runAgent command**

```typescript
// src/commands/runAgent.ts
import * as vscode from "vscode";
import { AstromeshCli } from "../cli";

export async function runAgent(cli: AstromeshCli): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  let agentName: string | undefined;

  // Try to extract agent name from active YAML file
  if (editor?.document.fileName.endsWith(".agent.yaml")) {
    const text = editor.document.getText();
    const match = text.match(/^\s*name:\s*(.+)$/m);
    if (match) agentName = match[1].trim();
  }

  if (!agentName) {
    agentName = await vscode.window.showInputBox({
      prompt: "Agent name",
      placeHolder: "e.g. my-agent",
    });
  }
  if (!agentName) return;

  const query = await vscode.window.showInputBox({
    prompt: "Query",
    placeHolder: "What do you want to ask?",
  });
  if (!query) return;

  const outputChannel = vscode.window.createOutputChannel("Astromesh");
  outputChannel.show(true);
  outputChannel.appendLine(`> astromeshctl run ${agentName} "${query}" --json`);

  const { data, error } = await cli.execJson("run", [agentName, query]);
  if (error) {
    outputChannel.appendLine(`Error: ${error}`);
    vscode.window.showErrorMessage(`Astromesh: ${error}`);
    return;
  }

  const result = data as Record<string, unknown>;
  outputChannel.appendLine(`Response: ${result.response ?? JSON.stringify(result)}`);
  if (result.trace_id) {
    outputChannel.appendLine(`Trace: ${result.trace_id}`);
  }
}
```

- [ ] **Step 2: Implement runWorkflow command**

```typescript
// src/commands/runWorkflow.ts
import * as vscode from "vscode";
import { AstromeshCli } from "../cli";

export async function runWorkflow(cli: AstromeshCli): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  let workflowName: string | undefined;

  if (editor?.document.fileName.endsWith(".workflow.yaml")) {
    const text = editor.document.getText();
    const match = text.match(/^\s*name:\s*(.+)$/m);
    if (match) workflowName = match[1].trim();
  }

  if (!workflowName) {
    workflowName = await vscode.window.showInputBox({
      prompt: "Workflow name",
      placeHolder: "e.g. lead-qualification-pipeline",
    });
  }
  if (!workflowName) return;

  const query = await vscode.window.showInputBox({
    prompt: "Trigger query (optional)",
    placeHolder: "Enter trigger data or leave empty",
  });

  const outputChannel = vscode.window.createOutputChannel("Astromesh");
  outputChannel.show(true);
  outputChannel.appendLine(`> astromeshctl run ${workflowName} --workflow --json`);

  const flags: Record<string, string | boolean> = { workflow: true };
  const positional = [workflowName];
  if (query) positional.push(query);

  const { data, error } = await cli.execJson("run", positional, flags);
  if (error) {
    outputChannel.appendLine(`Error: ${error}`);
    return;
  }

  const result = data as Record<string, unknown>;
  outputChannel.appendLine(`Status: ${result.status}`);
  outputChannel.appendLine(`Duration: ${result.duration_ms}ms`);
  outputChannel.appendLine(JSON.stringify(result, null, 2));
}
```

- [ ] **Step 3: Wire commands in extension.ts**

Replace the stub registrations in `extension.ts` for `runAgent` and `runWorkflow`:

```typescript
// In activate(), replace the stubs:
import { runAgent } from "./commands/runAgent";
import { runWorkflow } from "./commands/runWorkflow";

// Replace stub registrations:
vscode.commands.registerCommand("astromesh.runAgent", () => runAgent(cli)),
vscode.commands.registerCommand("astromesh.runWorkflow", () => runWorkflow(cli)),
```

- [ ] **Step 4: Build and verify**

```bash
cd vscode-extension && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add vscode-extension/src/commands/runAgent.ts vscode-extension/src/commands/runWorkflow.ts vscode-extension/src/extension.ts
git commit -m "feat(vscode): add run agent and run workflow commands"
```

---

### Task 7: Diagnostics Command

**Files:**
- Create: `vscode-extension/src/commands/diagnostics.ts`
- Modify: `vscode-extension/src/extension.ts`

- [ ] **Step 1: Implement diagnostics**

```typescript
// src/commands/diagnostics.ts
import * as vscode from "vscode";
import { AstromeshCli } from "../cli";

export async function showDiagnostics(cli: AstromeshCli): Promise<void> {
  const outputChannel = vscode.window.createOutputChannel("Astromesh Diagnostics");
  outputChannel.show(true);
  outputChannel.appendLine("Running astromesh doctor...\n");

  const { data, error } = await cli.execJson("doctor");
  if (error) {
    outputChannel.appendLine(`Error: ${error}`);
    vscode.window.showErrorMessage("Astromesh daemon not reachable. Is it running?");
    return;
  }

  const result = data as Record<string, unknown>;
  const healthy = result.healthy as boolean;
  const checks = result.checks as Record<string, { status: string; message: string }>;

  outputChannel.appendLine(healthy ? "Status: HEALTHY\n" : "Status: UNHEALTHY\n");

  for (const [name, check] of Object.entries(checks)) {
    const icon = check.status === "ok" ? "✓" : "✗";
    outputChannel.appendLine(`  ${icon} ${name}: ${check.status} — ${check.message}`);
  }

  if (healthy) {
    vscode.window.showInformationMessage("Astromesh: All checks passed");
  } else {
    vscode.window.showWarningMessage("Astromesh: Some checks failed — see output");
  }
}
```

- [ ] **Step 2: Wire in extension.ts**

```typescript
import { showDiagnostics } from "./commands/diagnostics";

// Replace stub:
vscode.commands.registerCommand("astromesh.doctor", () => showDiagnostics(cli)),
```

- [ ] **Step 3: Build and commit**

```bash
cd vscode-extension && npm run build
git add vscode-extension/src/commands/diagnostics.ts vscode-extension/src/extension.ts
git commit -m "feat(vscode): add diagnostics command wrapping astromesh doctor"
```

---

## Chunk 4: Traces Sidebar

### Task 8: Traces TreeDataProvider

**Files:**
- Create: `vscode-extension/src/views/tracesProvider.ts`
- Modify: `vscode-extension/src/extension.ts`

- [ ] **Step 1: Write traces tree test**

```typescript
// test/suite/traces.test.ts
import * as assert from "assert";
import { TraceItem, buildTraceTree } from "../../src/views/tracesProvider";

suite("TracesProvider", () => {
  test("buildTraceTree creates root items from trace list", () => {
    const traces = [
      { trace_id: "abc123", agent: "my-agent", status: "ok", duration_ms: 500 },
      { trace_id: "def456", agent: "other-agent", status: "error", duration_ms: 120 },
    ];
    const items = buildTraceTree(traces);
    assert.strictEqual(items.length, 2);
    assert.strictEqual(items[0].label, "abc123");
    assert.strictEqual(items[0].description, "my-agent — 500ms");
  });

  test("buildTraceTree handles empty list", () => {
    const items = buildTraceTree([]);
    assert.strictEqual(items.length, 0);
  });
});
```

- [ ] **Step 2: Implement TracesProvider**

```typescript
// src/views/tracesProvider.ts
import * as vscode from "vscode";

interface TraceData {
  trace_id: string;
  agent: string;
  status: string;
  duration_ms: number;
  spans?: SpanData[];
}

interface SpanData {
  name: string;
  duration_ms: number;
  status?: string;
  children?: SpanData[];
}

export class TraceItem extends vscode.TreeItem {
  constructor(
    public readonly label: string,
    public readonly description: string,
    public readonly collapsibleState: vscode.TreeItemCollapsibleState,
    public readonly children: TraceItem[] = []
  ) {
    super(label, collapsibleState);
  }
}

export function buildTraceTree(traces: TraceData[]): TraceItem[] {
  return traces.map((t) => {
    const hasSpans = t.spans && t.spans.length > 0;
    const state = hasSpans
      ? vscode.TreeItemCollapsibleState.Collapsed
      : vscode.TreeItemCollapsibleState.None;
    const children = hasSpans ? buildSpanItems(t.spans!) : [];
    const item = new TraceItem(
      t.trace_id.slice(0, 12),
      `${t.agent} — ${t.duration_ms}ms`,
      state,
      children
    );
    item.iconPath = new vscode.ThemeIcon(
      t.status === "ok" ? "pass" : "error"
    );
    return item;
  });
}

function buildSpanItems(spans: SpanData[]): TraceItem[] {
  return spans.map((s) => {
    const hasChildren = s.children && s.children.length > 0;
    const state = hasChildren
      ? vscode.TreeItemCollapsibleState.Collapsed
      : vscode.TreeItemCollapsibleState.None;
    const children = hasChildren ? buildSpanItems(s.children!) : [];
    return new TraceItem(s.name, `${s.duration_ms}ms`, state, children);
  });
}

export class TracesProvider implements vscode.TreeDataProvider<TraceItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<TraceItem | undefined>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
  private items: TraceItem[] = [];

  constructor(private readonly daemonUrl: string) {}

  refresh(): void {
    this.fetchTraces().then(() => this._onDidChangeTreeData.fire(undefined));
  }

  getTreeItem(element: TraceItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: TraceItem): TraceItem[] {
    if (!element) return this.items;
    return element.children;
  }

  private async fetchTraces(): Promise<void> {
    try {
      const resp = await fetch(`${this.daemonUrl}/v1/traces/?limit=20`);
      if (!resp.ok) { this.items = []; return; }
      const data = (await resp.json()) as { traces: TraceData[] };
      this.items = buildTraceTree(data.traces ?? []);
    } catch {
      this.items = [];
    }
  }
}
```

- [ ] **Step 3: Wire in extension.ts**

```typescript
import { TracesProvider } from "./views/tracesProvider";

// In activate():
const daemonUrl = config.get<string>("daemonUrl", "http://localhost:8000");
const tracesProvider = new TracesProvider(daemonUrl);
vscode.window.registerTreeDataProvider("astromesh.traces", tracesProvider);
tracesProvider.refresh();

// Auto-refresh
const autoRefresh = config.get<boolean>("traces.autoRefresh", true);
const interval = config.get<number>("traces.refreshInterval", 10);
if (autoRefresh) {
  const timer = setInterval(() => tracesProvider.refresh(), interval * 1000);
  context.subscriptions.push({ dispose: () => clearInterval(timer) });
}

// Replace refreshTraces stub:
vscode.commands.registerCommand("astromesh.refreshTraces", () => tracesProvider.refresh()),
```

- [ ] **Step 4: Build and run tests**

```bash
cd vscode-extension && npm run build && npx mocha dist/test/suite/traces.test.js
```

- [ ] **Step 5: Commit**

```bash
git add vscode-extension/src/views/tracesProvider.ts vscode-extension/test/suite/traces.test.ts vscode-extension/src/extension.ts
git commit -m "feat(vscode): add traces sidebar with auto-refresh tree view"
```

---

## Chunk 5: Webview Panels (Metrics + Workflow Visualizer)

### Task 9: Metrics Dashboard Webview

**Files:**
- Create: `vscode-extension/src/views/metricsPanel.ts`
- Create: `vscode-extension/webview/metrics.html`
- Modify: `vscode-extension/src/extension.ts`

- [ ] **Step 1: Create metrics webview HTML**

The HTML reuses the same dark theme as the built-in dashboard (`astromesh/api/routes/dashboard.py`), adapted for VS Code webview.

```html
<!-- webview/metrics.html -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  :root { --bg: var(--vscode-editor-background); --surface: var(--vscode-sideBar-background); --border: var(--vscode-panel-border); --text: var(--vscode-editor-foreground); --muted: var(--vscode-descriptionForeground); --accent: #00d4ff; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: var(--vscode-font-family); background: var(--bg); color: var(--text); padding: 1rem; }
  h1 { font-size: 1.1rem; margin-bottom: 1rem; }
  h1 span { color: var(--accent); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 0.75rem; margin-bottom: 1.5rem; }
  .counter { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 0.75rem; }
  .counter .label { font-size: 0.7rem; color: var(--muted); } .counter .value { font-size: 1.4rem; font-weight: 600; color: var(--accent); }
  table { width: 100%; border-collapse: collapse; font-size: 0.8rem; margin-bottom: 1rem; }
  th, td { text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 500; }
  .empty { color: var(--muted); font-style: italic; }
  #status { font-size: 0.7rem; color: var(--muted); margin-top: 1rem; }
</style>
</head>
<body>
<h1><span>Astromesh</span> Metrics</h1>
<h3>Counters</h3>
<div id="counters" class="grid"><span class="empty">Loading...</span></div>
<h3>Histograms</h3>
<div id="histograms"><span class="empty">Loading...</span></div>
<div id="status"></div>
<script>
  const vscode = acquireVsCodeApi();

  window.addEventListener("message", (event) => {
    const { counters, histograms } = event.data;
    renderCounters(counters || {});
    renderHistograms(histograms || {});
    document.getElementById("status").textContent = "Updated: " + new Date().toLocaleTimeString();
  });

  function renderCounters(c) {
    const el = document.getElementById("counters");
    const keys = Object.keys(c);
    if (!keys.length) { el.innerHTML = '<span class="empty">No counters</span>'; return; }
    el.innerHTML = keys.map(k => `<div class="counter"><div class="label">${k}</div><div class="value">${c[k]}</div></div>`).join("");
  }

  function renderHistograms(h) {
    const el = document.getElementById("histograms");
    const keys = Object.keys(h);
    if (!keys.length) { el.innerHTML = '<span class="empty">No histograms</span>'; return; }
    let html = "<table><tr><th>Metric</th><th>Count</th><th>Avg</th><th>Min</th><th>Max</th></tr>";
    for (const [k, v] of Object.entries(h)) {
      html += `<tr><td>${k}</td><td>${v.count}</td><td>${v.avg?.toFixed(1)??"-"}</td><td>${v.min?.toFixed(1)??"-"}</td><td>${v.max?.toFixed(1)??"-"}</td></tr>`;
    }
    el.innerHTML = html + "</table>";
  }

  vscode.postMessage({ type: "ready" });
</script>
</body>
</html>
```

- [ ] **Step 2: Implement MetricsPanel**

```typescript
// src/views/metricsPanel.ts
import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";

export class MetricsPanel {
  private static instance: MetricsPanel | undefined;
  private panel: vscode.WebviewPanel;
  private timer: ReturnType<typeof setInterval> | undefined;

  private constructor(
    extensionPath: string,
    private readonly daemonUrl: string
  ) {
    this.panel = vscode.window.createWebviewPanel(
      "astromeshMetrics",
      "Astromesh Metrics",
      vscode.ViewColumn.Two,
      { enableScripts: true, retainContextWhenHidden: true }
    );

    const htmlPath = path.join(extensionPath, "webview", "metrics.html");
    this.panel.webview.html = fs.readFileSync(htmlPath, "utf-8");

    this.panel.webview.onDidReceiveMessage((msg) => {
      if (msg.type === "ready") this.refresh();
    });

    this.timer = setInterval(() => this.refresh(), 10000);
    this.panel.onDidDispose(() => {
      if (this.timer) clearInterval(this.timer);
      MetricsPanel.instance = undefined;
    });
  }

  static show(extensionPath: string, daemonUrl: string): void {
    if (MetricsPanel.instance) {
      MetricsPanel.instance.panel.reveal();
      return;
    }
    MetricsPanel.instance = new MetricsPanel(extensionPath, daemonUrl);
  }

  private async refresh(): Promise<void> {
    try {
      const resp = await fetch(`${this.daemonUrl}/v1/metrics/`);
      if (!resp.ok) return;
      const data = await resp.json();
      this.panel.webview.postMessage(data);
    } catch {
      // daemon unreachable — silent
    }
  }
}
```

- [ ] **Step 3: Wire in extension.ts**

```typescript
import { MetricsPanel } from "./views/metricsPanel";

// Replace stub:
vscode.commands.registerCommand("astromesh.showMetrics", () =>
  MetricsPanel.show(context.extensionPath, daemonUrl)
),
```

- [ ] **Step 4: Build and commit**

```bash
cd vscode-extension && npm run build
git add vscode-extension/src/views/metricsPanel.ts vscode-extension/webview/metrics.html vscode-extension/src/extension.ts
git commit -m "feat(vscode): add metrics dashboard webview panel"
```

---

### Task 10: Workflow Visualizer Webview

**Files:**
- Create: `vscode-extension/src/views/workflowPanel.ts`
- Create: `vscode-extension/webview/workflow.html`
- Modify: `vscode-extension/src/extension.ts`

- [ ] **Step 1: Create workflow visualizer HTML**

Renders workflow YAML steps as a vertical DAG with connecting lines. Parses YAML from the VS Code message.

```html
<!-- webview/workflow.html -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  :root { --bg: var(--vscode-editor-background); --surface: var(--vscode-sideBar-background); --border: var(--vscode-panel-border); --text: var(--vscode-editor-foreground); --muted: var(--vscode-descriptionForeground); --accent: #00d4ff; --agent: #3fb950; --tool: #d29922; --switch: #a371f7; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: var(--vscode-font-family); background: var(--bg); color: var(--text); padding: 1.5rem; }
  h1 { font-size: 1.1rem; margin-bottom: 1rem; } h1 span { color: var(--accent); }
  .dag { display: flex; flex-direction: column; align-items: center; gap: 0; }
  .step { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem 1.25rem; min-width: 220px; text-align: center; position: relative; }
  .step .name { font-weight: 600; font-size: 0.9rem; }
  .step .type { font-size: 0.7rem; padding: 0.1rem 0.4rem; border-radius: 3px; display: inline-block; margin-top: 0.3rem; }
  .step.agent { border-left: 3px solid var(--agent); } .step.agent .type { background: #23863620; color: var(--agent); }
  .step.tool { border-left: 3px solid var(--tool); } .step.tool .type { background: #d2992220; color: var(--tool); }
  .step.switch { border-left: 3px solid var(--switch); } .step.switch .type { background: #a371f720; color: var(--switch); }
  .connector { width: 2px; height: 24px; background: var(--border); }
  .arrow { width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid var(--border); }
  .goto-label { font-size: 0.65rem; color: var(--muted); font-style: italic; margin-top: 0.2rem; }
  .empty { color: var(--muted); font-style: italic; text-align: center; margin-top: 2rem; }
</style>
</head>
<body>
<h1><span>Workflow</span> <span id="wf-name"></span></h1>
<div id="dag" class="dag"><span class="empty">Open a .workflow.yaml file and run "Astromesh: Visualize Workflow"</span></div>
<script>
  const vscode = acquireVsCodeApi();

  window.addEventListener("message", (event) => {
    const { name, steps } = event.data;
    document.getElementById("wf-name").textContent = name || "";
    renderDag(steps || []);
  });

  function renderDag(steps) {
    const el = document.getElementById("dag");
    if (!steps.length) { el.innerHTML = '<span class="empty">No steps found</span>'; return; }
    let html = "";
    steps.forEach((step, i) => {
      const type = step.agent ? "agent" : step.tool ? "tool" : "switch";
      const target = step.agent || step.tool || "switch";
      html += `<div class="step ${type}"><div class="name">${step.name}</div><div class="type">${type}: ${target}</div>`;
      if (step.on_error) html += `<div class="goto-label">on_error → ${step.on_error}</div>`;
      if (type === "switch" && step.switch) {
        step.switch.forEach(c => {
          const label = c.when ? c.when.replace(/\\{\\{|\\}\\}/g, "") : "default";
          html += `<div class="goto-label">${label.trim().slice(0,40)} → ${c.goto}</div>`;
        });
      }
      html += "</div>";
      if (i < steps.length - 1) html += '<div class="connector"></div><div class="arrow"></div>';
    });
    el.innerHTML = html;
  }

  vscode.postMessage({ type: "ready" });
</script>
</body>
</html>
```

- [ ] **Step 2: Implement WorkflowPanel**

```typescript
// src/views/workflowPanel.ts
import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";

export class WorkflowPanel {
  private static instance: WorkflowPanel | undefined;
  private panel: vscode.WebviewPanel;

  private constructor(extensionPath: string) {
    this.panel = vscode.window.createWebviewPanel(
      "astromeshWorkflow",
      "Astromesh Workflow",
      vscode.ViewColumn.Two,
      { enableScripts: true }
    );

    const htmlPath = path.join(extensionPath, "webview", "workflow.html");
    this.panel.webview.html = fs.readFileSync(htmlPath, "utf-8");

    this.panel.onDidDispose(() => {
      WorkflowPanel.instance = undefined;
    });
  }

  static show(extensionPath: string): WorkflowPanel {
    if (WorkflowPanel.instance) {
      WorkflowPanel.instance.panel.reveal();
      return WorkflowPanel.instance;
    }
    WorkflowPanel.instance = new WorkflowPanel(extensionPath);
    return WorkflowPanel.instance;
  }

  sendWorkflowData(name: string, steps: unknown[]): void {
    this.panel.webview.postMessage({ name, steps });
  }
}

export async function showWorkflowVisualizer(extensionPath: string): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor?.document.fileName.endsWith(".workflow.yaml")) {
    vscode.window.showWarningMessage("Open a .workflow.yaml file first");
    return;
  }

  const text = editor.document.getText();

  // Simple YAML parsing for steps — extract name and type from each step block
  const nameMatch = text.match(/^\s*name:\s*(.+)$/m);
  const workflowName = nameMatch ? nameMatch[1].trim() : "unknown";

  // Parse steps array from YAML (simplified: look for step blocks under steps:)
  const steps: unknown[] = [];
  const stepRegex = /- name:\s*(.+)/g;
  let match;
  while ((match = stepRegex.exec(text)) !== null) {
    const stepName = match[1].trim();
    // Look ahead for agent/tool/switch
    const afterMatch = text.slice(match.index, match.index + 300);
    const agentMatch = afterMatch.match(/agent:\s*(.+)/);
    const toolMatch = afterMatch.match(/tool:\s*(.+)/);
    const switchMatch = afterMatch.match(/switch:/);
    const onErrorMatch = afterMatch.match(/on_error:\s*(.+)/);

    steps.push({
      name: stepName,
      agent: agentMatch ? agentMatch[1].trim() : undefined,
      tool: toolMatch && !agentMatch ? toolMatch[1].trim() : undefined,
      switch: switchMatch ? [] : undefined,
      on_error: onErrorMatch ? onErrorMatch[1].trim() : undefined,
    });
  }

  const panel = WorkflowPanel.show(extensionPath);
  // Small delay to ensure webview is ready
  setTimeout(() => panel.sendWorkflowData(workflowName, steps), 200);
}
```

- [ ] **Step 3: Wire in extension.ts**

```typescript
import { showWorkflowVisualizer } from "./views/workflowPanel";

// Replace stub:
vscode.commands.registerCommand("astromesh.showWorkflow", () =>
  showWorkflowVisualizer(context.extensionPath)
),
```

- [ ] **Step 4: Build and commit**

```bash
cd vscode-extension && npm run build
git add vscode-extension/src/views/workflowPanel.ts vscode-extension/webview/workflow.html vscode-extension/src/extension.ts
git commit -m "feat(vscode): add workflow visualizer DAG webview panel"
```

---

## Chunk 6: Copilot Chat + Final Assembly

### Task 11: Copilot Chat Panel

**Files:**
- Create: `vscode-extension/src/commands/copilot.ts`
- Create: `vscode-extension/webview/copilot.html`
- Modify: `vscode-extension/src/extension.ts`

- [ ] **Step 1: Create copilot chat HTML**

```html
<!-- webview/copilot.html -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  :root { --bg: var(--vscode-editor-background); --surface: var(--vscode-sideBar-background); --border: var(--vscode-panel-border); --text: var(--vscode-editor-foreground); --muted: var(--vscode-descriptionForeground); --accent: #00d4ff; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: var(--vscode-font-family); background: var(--bg); color: var(--text); display: flex; flex-direction: column; height: 100vh; }
  .header { padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); font-size: 0.9rem; font-weight: 600; }
  .header span { color: var(--accent); }
  .messages { flex: 1; overflow-y: auto; padding: 1rem; }
  .msg { margin-bottom: 0.75rem; padding: 0.6rem 0.8rem; border-radius: 6px; font-size: 0.85rem; line-height: 1.4; white-space: pre-wrap; }
  .msg.user { background: var(--surface); border: 1px solid var(--border); margin-left: 2rem; }
  .msg.assistant { background: transparent; border-left: 2px solid var(--accent); padding-left: 0.8rem; margin-right: 2rem; }
  .msg.loading { color: var(--muted); font-style: italic; }
  .input-area { display: flex; gap: 0.5rem; padding: 0.75rem 1rem; border-top: 1px solid var(--border); }
  input { flex: 1; background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 0.5rem 0.75rem; border-radius: 4px; font-size: 0.85rem; outline: none; }
  input:focus { border-color: var(--accent); }
  button { background: var(--accent); color: #000; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 0.8rem; }
  button:disabled { opacity: 0.5; cursor: default; }
</style>
</head>
<body>
<div class="header"><span>Astromesh</span> Copilot</div>
<div class="messages" id="messages"></div>
<div class="input-area">
  <input id="input" type="text" placeholder="Ask anything about your agents..." />
  <button id="send" onclick="send()">Send</button>
</div>
<script>
  const vscode = acquireVsCodeApi();
  const messages = document.getElementById("messages");
  const input = document.getElementById("input");
  const sendBtn = document.getElementById("send");

  function addMessage(text, role) {
    const div = document.createElement("div");
    div.className = "msg " + role;
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return div;
  }

  function send() {
    const text = input.value.trim();
    if (!text) return;
    addMessage(text, "user");
    input.value = "";
    sendBtn.disabled = true;
    const loading = addMessage("Thinking...", "loading");
    vscode.postMessage({ type: "ask", query: text });
  }

  input.addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });

  window.addEventListener("message", (event) => {
    const { type, response, error } = event.data;
    // Remove loading message
    const loading = messages.querySelector(".loading");
    if (loading) loading.remove();
    sendBtn.disabled = false;

    if (type === "response") {
      addMessage(response, "assistant");
    } else if (type === "error") {
      addMessage("Error: " + error, "assistant");
    }
  });
</script>
</body>
</html>
```

- [ ] **Step 2: Implement copilot command**

```typescript
// src/commands/copilot.ts
import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import { AstromeshCli } from "../cli";

let copilotPanel: vscode.WebviewPanel | undefined;

export function showCopilot(extensionPath: string, cli: AstromeshCli): void {
  if (copilotPanel) {
    copilotPanel.reveal();
    return;
  }

  copilotPanel = vscode.window.createWebviewPanel(
    "astromeshCopilot",
    "Astromesh Copilot",
    vscode.ViewColumn.Two,
    { enableScripts: true, retainContextWhenHidden: true }
  );

  const htmlPath = path.join(extensionPath, "webview", "copilot.html");
  copilotPanel.webview.html = fs.readFileSync(htmlPath, "utf-8");

  copilotPanel.webview.onDidReceiveMessage(async (msg) => {
    if (msg.type !== "ask") return;

    const { data, error } = await cli.execJson("ask", [msg.query]);
    if (error) {
      copilotPanel?.webview.postMessage({ type: "error", error });
      return;
    }

    const result = data as Record<string, unknown>;
    const response = (result.response as string) ?? JSON.stringify(result);
    copilotPanel?.webview.postMessage({ type: "response", response });
  });

  copilotPanel.onDidDispose(() => {
    copilotPanel = undefined;
  });
}
```

- [ ] **Step 3: Wire in extension.ts**

```typescript
import { showCopilot } from "./commands/copilot";

// Replace stub:
vscode.commands.registerCommand("astromesh.copilot", () =>
  showCopilot(context.extensionPath, cli)
),
```

- [ ] **Step 4: Build and commit**

```bash
cd vscode-extension && npm run build
git add vscode-extension/src/commands/copilot.ts vscode-extension/webview/copilot.html vscode-extension/src/extension.ts
git commit -m "feat(vscode): add copilot chat panel with CLI integration"
```

---

### Task 12: Final Extension Assembly + README

**Files:**
- Modify: `vscode-extension/src/extension.ts` (final cleanup — all stubs replaced)
- Create: `vscode-extension/README.md`

- [ ] **Step 1: Write extension README**

```markdown
# Astromesh for VS Code

The official VS Code extension for [Astromesh](https://github.com/monaccode/astromesh) — AI Agent Runtime Platform.

## Features

### YAML IntelliSense
Auto-completion and validation for `*.agent.yaml` and `*.workflow.yaml` files. Requires the [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml).

### Run Agent
Click the play button on any `.agent.yaml` file to execute the agent. Results appear in the output panel.

### Workflow Visualizer
Open a `.workflow.yaml` file and click the play button to see a visual DAG of your workflow steps.

### Traces Panel
Expandable span tree in the sidebar showing recent execution traces with auto-refresh.

### Metrics Dashboard
Webview panel displaying counters and histograms from the Astromesh runtime.

### Copilot Chat
Interactive chat panel powered by `astromesh ask` — get help building and debugging agents.

### Diagnostics
Run `Astromesh: Diagnostics` to check daemon status, providers, and connections.

## Requirements

- [Astromesh](https://github.com/monaccode/astromesh) installed and running
- `astromeshctl` available in PATH (or configure `astromesh.cliPath`)
- [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) for IntelliSense

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `astromesh.cliPath` | `astromeshctl` | Path to CLI binary |
| `astromesh.daemonUrl` | `http://localhost:8000` | Daemon URL |
| `astromesh.traces.autoRefresh` | `true` | Auto-refresh traces |
| `astromesh.traces.refreshInterval` | `10` | Refresh interval (seconds) |
```

- [ ] **Step 2: Verify final extension.ts has all imports and no stubs**

Clean up `extension.ts` to ensure all 7 commands are properly wired (no "coming soon" stubs).

- [ ] **Step 3: Build, package, and verify**

```bash
cd vscode-extension && npm run build && npx vsce package --no-dependencies
```
Expected: `astromesh-0.1.0.vsix` generated.

- [ ] **Step 4: Commit**

```bash
git add vscode-extension/README.md vscode-extension/src/extension.ts
git commit -m "feat(vscode): finalize extension with README and assembly"
```

---

## Chunk 7: Documentation + Project README Update

### Task 13: Add VS Code Extension Docs to docs-site

**Files:**
- Create: `docs-site/src/content/docs/reference/os/vscode-extension.md`
- Modify: `docs-site/astro.config.mjs` (add sidebar entry)

- [ ] **Step 1: Write VS Code extension documentation page**

Follow the existing docs-site style (frontmatter, step-by-step, code blocks, tables). Document all 7 features with screenshots placeholder text and usage instructions.

```markdown
---
title: VS Code Extension
description: YAML IntelliSense, workflow visualization, traces, metrics, and copilot — all inside VS Code.
---

Astromesh ships a VS Code extension that brings the full developer experience into your editor. The extension wraps `astromeshctl` — no business logic runs in VS Code itself.

## Installation

Install from the VS Code marketplace:

1. Open VS Code
2. Press `Ctrl+Shift+X` (Extensions)
3. Search for "Astromesh"
4. Click Install

Or install from VSIX:

\`\`\`bash
code --install-extension astromesh-0.1.0.vsix
\`\`\`

### Prerequisites

- Astromesh daemon running (`astromeshd` or `uv run uvicorn astromesh.api.main:app`)
- `astromeshctl` in PATH
- [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) for IntelliSense

## Features

### YAML IntelliSense

The extension provides JSON Schemas for `*.agent.yaml` and `*.workflow.yaml` files. With the YAML extension installed, you get:

- Auto-completion for all fields
- Validation errors on invalid values
- Hover documentation for each property

Works automatically — no configuration needed.

### Run Agent

Open any `.agent.yaml` file and click the play button in the editor title bar. The extension:

1. Extracts the agent name from the YAML
2. Prompts for a query
3. Runs `astromeshctl run <agent> "<query>" --json`
4. Shows the response in the Output panel

You can also run via Command Palette: `Astromesh: Run Agent`.

### Workflow Visualizer

Open a `.workflow.yaml` file and click the play button. A webview panel opens showing your workflow as a visual DAG:

- Agent steps in green
- Tool steps in yellow
- Switch steps in purple
- Error handlers and goto labels shown inline

### Traces Panel

The Astromesh activity bar icon opens the Traces sidebar. It shows recent execution traces as an expandable tree:

- Root level: trace ID, agent name, duration
- Expand to see individual spans with timing
- Auto-refreshes every 10 seconds (configurable)
- Click refresh icon to update manually

### Metrics Dashboard

Run `Astromesh: Metrics Dashboard` to open a webview showing:

- Counter metrics (agent runs, tool calls, tokens)
- Histogram metrics (latency, iterations)
- Auto-refreshes every 10 seconds

### Copilot Chat

Run `Astromesh: Ask Copilot` to open an interactive chat panel. The copilot can help with:

- Agent configuration questions
- Debugging trace issues
- Workflow design
- Tool usage examples

### Diagnostics

Run `Astromesh: Diagnostics` to check system health. Equivalent to `astromeshctl doctor`.

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `astromesh.cliPath` | `astromeshctl` | Path to the CLI binary |
| `astromesh.daemonUrl` | `http://localhost:8000` | Astromesh daemon URL |
| `astromesh.traces.autoRefresh` | `true` | Auto-refresh traces panel |
| `astromesh.traces.refreshInterval` | `10` | Refresh interval in seconds |
```

- [ ] **Step 2: Add sidebar entry in astro.config.mjs**

Add `{ label: "VS Code Extension", slug: "reference/os/vscode-extension" }` after the CLI entry in the Reference > Astromesh OS section.

- [ ] **Step 3: Build docs-site and verify**

```bash
cd docs-site && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add docs-site/src/content/docs/reference/os/vscode-extension.md docs-site/astro.config.mjs
git commit -m "docs: add VS Code extension reference page to docs-site"
```

---

### Task 14: Update Project README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add Developer Experience section to README**

Add a new section after "Observability" and before "Architecture":

```markdown
---

### Developer Experience

Astromesh provides a complete developer toolkit:

| Tool | Description |
|------|-------------|
| **CLI** (`astromeshctl`) | Scaffold agents, run workflows, inspect traces, view metrics, validate configs |
| **Copilot** | Built-in AI assistant that helps build and debug agents |
| **VS Code Extension** | YAML IntelliSense, workflow visualizer, traces panel, metrics dashboard, copilot chat |
| **Built-in Dashboard** | Web UI at `/v1/dashboard/` with real-time observability |

```bash
# Scaffold a new agent
astromeshctl new agent customer-support

# Run it
astromeshctl run customer-support "How do I reset my password?"

# See what happened
astromeshctl traces customer-support --last 5

# Check costs
astromeshctl cost --window 24h

# Ask the copilot for help
astromeshctl ask "Why is my agent slow?"
```

---
```

- [ ] **Step 2: Update Tool System section**

Replace the existing Tool System section to reflect the current state:

```markdown
### Tool System

Agents interact with external systems using tools:

| Type | Description |
|------|-------------|
| **Built-in** (18 tools) | web_search, http_request, sql_query, send_email, read_file, and more |
| **MCP Servers** (3) | code_interpreter, shell_exec, generate_image |
| **Agent tools** | Invoke other agents as tools for multi-agent composition |
| **Webhooks** | Call external HTTP endpoints |
| **RAG** | Query and ingest documents |

Tools are configured declaratively in agent YAML with zero-code setup for built-ins.
```

- [ ] **Step 3: Update Observability section**

```markdown
### Observability

Full observability stack with zero configuration:

- **Structured tracing** — span trees for every agent execution
- **Metrics** — counters and histograms (runs, tokens, cost, latency)
- **Built-in dashboard** — web UI at `/v1/dashboard/`
- **CLI access** — `astromeshctl traces`, `astromeshctl metrics`, `astromeshctl cost`
- **OpenTelemetry export** — compatible with Jaeger, Grafana Tempo, etc.
- **VS Code integration** — traces panel and metrics dashboard in your editor
```

- [ ] **Step 4: Update Roadmap section**

Replace existing roadmap with updated items:

```markdown
## Roadmap

- [x] Multi-model runtime with 6 providers
- [x] 6 orchestration patterns (ReAct, Plan&Execute, Pipeline, Fan-Out, Supervisor, Swarm)
- [x] Memory system (conversational, semantic, episodic)
- [x] RAG pipeline with 4 vector stores
- [x] 18 built-in tools + 3 MCP servers
- [x] Full observability (tracing, metrics, dashboard)
- [x] CLI with copilot
- [x] Multi-agent composition (agent-as-tool)
- [x] Workflow YAML engine
- [x] VS Code extension
- [ ] Distributed agent execution
- [ ] GPU-aware model scheduling
- [ ] Event-driven agents
- [ ] Multi-tenant runtime
- [ ] Agent marketplace
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: update README with developer experience, tools, and roadmap"
```

---

### Task 15: Add Developer Tools Guide to docs-site

**Files:**
- Create: `docs-site/src/content/docs/getting-started/developer-tools.md`
- Modify: `docs-site/astro.config.mjs` (add to Getting Started section)

- [ ] **Step 1: Write developer tools overview page**

This is a "value proposition" page — shows the complete developer workflow from scaffolding to production monitoring, using all tools together. Style: step-by-step like quickstart.md but focused on the tooling story.

```markdown
---
title: Developer Tools
description: CLI, Copilot, VS Code extension, and dashboard — everything you need to build agents.
---

Astromesh gives you a complete toolkit for building, running, and monitoring AI agents. This guide walks through the developer workflow from start to finish.

## The Workflow

```
Define → Run → Debug → Optimize → Deploy
  │        │       │         │         │
  YAML   CLI    Traces    Metrics   Docker/K8s
  │        │       │         │
  VS Code IntelliSense  Dashboard
```

## Step 1: Scaffold

Create a new agent in seconds:

\`\`\`bash
astromeshctl new agent customer-support
\`\`\`

This generates a ready-to-run YAML file in `config/agents/`. Open it in VS Code for IntelliSense — auto-completion and validation for every field.

## Step 2: Run

\`\`\`bash
astromeshctl run customer-support "How do I reset my password?"
\`\`\`

Or click the play button directly in VS Code on your `.agent.yaml` file.

## Step 3: Debug

See exactly what happened inside:

\`\`\`bash
astromeshctl traces customer-support --last 5
\`\`\`

Each trace shows the full execution tree — guardrails, memory, LLM calls, tool usage, and timings. In VS Code, the Traces panel shows this as an expandable tree in the sidebar.

## Step 4: Optimize

Check token usage and costs:

\`\`\`bash
astromeshctl metrics customer-support
astromeshctl cost --window 24h
\`\`\`

The Metrics Dashboard (in VS Code or at `/v1/dashboard/`) shows counters and histograms in real-time.

## Step 5: Ask the Copilot

Stuck on something? The built-in copilot knows your project:

\`\`\`bash
astromeshctl ask "Why is my agent using so many tokens?"
\`\`\`

Or use the Copilot Chat panel in VS Code for an interactive session.

## Multi-Agent Workflows

When one agent isn't enough, compose them:

\`\`\`yaml
tools:
  - name: qualify-lead
    type: agent
    agent: sales-qualifier
\`\`\`

Or define a full pipeline in Workflow YAML:

\`\`\`bash
astromeshctl new workflow lead-pipeline
astromeshctl run lead-pipeline --workflow --input '{"company": "Acme"}'
\`\`\`

Visualize the DAG in VS Code with the Workflow Visualizer.

## Tool Summary

| Tool | What it does |
|------|--------------|
| `astromeshctl` | CLI for everything — scaffold, run, debug, monitor |
| Copilot | AI assistant that knows Astromesh |
| VS Code Extension | IntelliSense, traces, metrics, workflow viz, copilot chat |
| Dashboard | Web UI at `/v1/dashboard/` |

:::tip[Future: Cluster Orchestration]
The VS Code extension is designed to connect to remote Astromesh clusters. In upcoming releases, you'll be able to deploy, monitor, and orchestrate agents across your production environment — all from your editor.
:::
```

- [ ] **Step 2: Add sidebar entry**

Add `{ label: "Developer Tools", slug: "getting-started/developer-tools" }` after "First Agent" in the Getting Started section of `astro.config.mjs`.

- [ ] **Step 3: Build docs-site and verify**

```bash
cd docs-site && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add docs-site/src/content/docs/getting-started/developer-tools.md docs-site/astro.config.mjs
git commit -m "docs: add developer tools guide to docs-site getting started"
```

---

### Task 16: Add to docs/ Directory

**Files:**
- Create: `docs/DEVELOPER_TOOLS.md`

- [ ] **Step 1: Write developer tools doc for docs/ directory**

This is a concise version for the repo docs (which complement the full docs-site). Follow the pattern of existing files in `docs/` (TECH_OVERVIEW.md, DEV_QUICKSTART.md, etc.).

```markdown
# Developer Tools

Astromesh includes a complete developer toolkit for building, running, and monitoring AI agents.

## CLI (`astromeshctl`)

The CLI is the primary interface for all operations:

| Command | Description |
|---------|-------------|
| `new agent <name>` | Scaffold a new agent YAML |
| `new workflow <name>` | Scaffold a workflow YAML |
| `new tool <name>` | Scaffold a custom tool |
| `run <agent> "query"` | Execute an agent |
| `run <name> --workflow` | Execute a workflow |
| `dev` | Hot-reload development server |
| `traces <agent> --last N` | View recent traces |
| `trace <id>` | Inspect a trace span tree |
| `metrics <agent>` | View agent metrics |
| `cost --window 24h` | Cost summary |
| `tools list` | List available tools |
| `tools test <name> '{}'` | Test a tool in isolation |
| `validate` | Validate all project YAMLs |
| `doctor` | Check system health |
| `ask "question"` | Ask the copilot |

Install: `uv sync --extra cli`

## Copilot

The copilot is an Astromesh agent that helps you build agents. It can:

- Answer configuration questions
- Debug execution traces
- Suggest optimizations
- Generate YAML scaffolding

Usage: `astromeshctl ask "How do I add memory to my agent?"`

## VS Code Extension

Install from the marketplace or from a `.vsix` file.

Features:

- **YAML IntelliSense** — auto-completion for `.agent.yaml` and `.workflow.yaml`
- **Run Agent** — play button on agent files
- **Workflow Visualizer** — DAG view of workflow steps
- **Traces Panel** — sidebar with expandable span trees
- **Metrics Dashboard** — webview with counters and histograms
- **Copilot Chat** — interactive chat panel
- **Diagnostics** — system health check

Settings:
- `astromesh.cliPath` — path to CLI binary (default: `astromeshctl`)
- `astromesh.daemonUrl` — daemon URL (default: `http://localhost:8000`)

## Dashboard

Built-in web UI at `http://localhost:8000/v1/dashboard/` with:

- Counter metrics
- Histogram tables
- Recent traces with status
- Workflow list

Auto-refreshes every 10 seconds.
```

- [ ] **Step 2: Add reference in README**

Add to the documentation links section in README:

```markdown
- **Developer tools**: [`docs/DEVELOPER_TOOLS.md`](docs/DEVELOPER_TOOLS.md)
```

- [ ] **Step 3: Commit**

```bash
git add docs/DEVELOPER_TOOLS.md README.md
git commit -m "docs: add developer tools reference to docs/ directory"
```

---

**Total: 16 tasks across 7 chunks.**

- Chunks 1-6: VS Code extension implementation (12 tasks)
- Chunk 7: Documentation + README updates (4 tasks)

Dependencies:
- Tasks 1-3 must be sequential (scaffold → cli wrapper → entry point)
- Tasks 4-5 are independent (schemas)
- Tasks 6-7 depend on Task 2 (CLI wrapper)
- Task 8 depends on Task 3 (extension entry point)
- Tasks 9-11 depend on Task 3
- Task 12 depends on all previous extension tasks
- Tasks 13-16 can run in parallel after Task 12
