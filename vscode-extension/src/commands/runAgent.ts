import * as vscode from "vscode";
import { AstromeshCli } from "../cli";

export async function runAgent(cli: AstromeshCli): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  let agentName: string | undefined;

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
