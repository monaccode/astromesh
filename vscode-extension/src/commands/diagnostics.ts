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
