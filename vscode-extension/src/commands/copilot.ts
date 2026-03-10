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
