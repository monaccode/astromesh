import * as vscode from "vscode";
import { AstromeshCli } from "./cli";
import { StatusBarManager } from "./statusBar";
import { runAgent } from "./commands/runAgent";
import { runWorkflow } from "./commands/runWorkflow";
import { showDiagnostics } from "./commands/diagnostics";
import { showCopilot } from "./commands/copilot";
import { TracesProvider } from "./views/tracesProvider";
import { MetricsPanel } from "./views/metricsPanel";
import { showWorkflowVisualizer } from "./views/workflowPanel";

let statusBar: StatusBarManager | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const config = vscode.workspace.getConfiguration("astromesh");
  const cliPath = config.get<string>("cliPath", "astromeshctl");
  const daemonUrl = config.get<string>("daemonUrl", "http://localhost:8000");
  const cli = new AstromeshCli(cliPath);

  // Status bar
  statusBar = new StatusBarManager(cli);
  statusBar.startAutoRefresh(30);
  context.subscriptions.push({ dispose: () => statusBar?.dispose() });

  // Traces sidebar
  const tracesProvider = new TracesProvider(daemonUrl);
  vscode.window.registerTreeDataProvider("astromesh.traces", tracesProvider);
  tracesProvider.refresh();

  const autoRefresh = config.get<boolean>("traces.autoRefresh", true);
  const interval = config.get<number>("traces.refreshInterval", 10);
  if (autoRefresh) {
    const timer = setInterval(() => tracesProvider.refresh(), interval * 1000);
    context.subscriptions.push({ dispose: () => clearInterval(timer) });
  }

  // Commands
  context.subscriptions.push(
    vscode.commands.registerCommand("astromesh.runAgent", () => runAgent(cli)),
    vscode.commands.registerCommand("astromesh.runWorkflow", () => runWorkflow(cli)),
    vscode.commands.registerCommand("astromesh.doctor", () => showDiagnostics(cli)),
    vscode.commands.registerCommand("astromesh.copilot", () =>
      showCopilot(context.extensionPath, cli)
    ),
    vscode.commands.registerCommand("astromesh.showMetrics", () =>
      MetricsPanel.show(context.extensionPath, daemonUrl)
    ),
    vscode.commands.registerCommand("astromesh.showWorkflow", () =>
      showWorkflowVisualizer(context.extensionPath)
    ),
    vscode.commands.registerCommand("astromesh.refreshTraces", () =>
      tracesProvider.refresh()
    )
  );
}

export function deactivate(): void {
  statusBar?.dispose();
}
