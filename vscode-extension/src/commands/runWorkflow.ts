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
