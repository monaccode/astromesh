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
