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
