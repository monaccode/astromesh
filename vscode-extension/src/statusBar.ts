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
