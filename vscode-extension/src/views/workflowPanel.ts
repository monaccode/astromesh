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
  const nameMatch = text.match(/^\s*name:\s*(.+)$/m);
  const workflowName = nameMatch ? nameMatch[1].trim() : "unknown";

  const steps: unknown[] = [];
  const stepRegex = /- name:\s*(.+)/g;
  let match;
  while ((match = stepRegex.exec(text)) !== null) {
    const stepName = match[1].trim();
    const afterMatch = text.slice(match.index, match.index + 300);
    const agentMatch = afterMatch.match(/agent:\s*(.+)/);
    const toolMatch = afterMatch.match(/tool:\s*(.+)/);
    const switchMatch = afterMatch.match(/switch:/);
    const onErrorMatch = afterMatch.match(/on_error:\s*(.+)/);

    steps.push({
      name: stepName,
      agent: agentMatch ? agentMatch[1].trim() : undefined,
      tool: toolMatch && !agentMatch ? toolMatch[1].trim() : undefined,
      switch: switchMatch ? true : undefined,
      on_error: onErrorMatch ? onErrorMatch[1].trim() : undefined,
    });
  }

  const panel = WorkflowPanel.show(extensionPath);
  setTimeout(() => panel.sendWorkflowData(workflowName, steps), 200);
}
