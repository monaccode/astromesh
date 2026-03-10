"""Built-in observability dashboard served as inline HTML."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Astromesh Dashboard</title>
<style>
  :root { --bg: #0d1117; --surface: #161b22; --border: #30363d; --text: #e6edf3; --muted: #8b949e; --accent: #00d4ff; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); }
  header { padding: 1rem 2rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
  header h1 { font-size: 1.25rem; } header h1 span { color: var(--accent); }
  #status { font-size: 0.8rem; color: var(--muted); }
  main { max-width: 1200px; margin: 0 auto; padding: 1.5rem; display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.25rem; }
  .card h2 { font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin-bottom: 0.75rem; }
  .card.full { grid-column: 1 / -1; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 500; }
  .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem; }
  .badge-ok { background: #23863633; color: #3fb950; }
  .badge-err { background: #f8514933; color: #f85149; }
  .counter-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.75rem; }
  .counter { background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 0.75rem; }
  .counter .label { font-size: 0.75rem; color: var(--muted); } .counter .value { font-size: 1.5rem; font-weight: 600; color: var(--accent); }
  .span-tree { font-family: monospace; font-size: 0.8rem; line-height: 1.6; }
  .span-tree .indent { color: var(--border); } .span-tree .name { color: var(--accent); } .span-tree .dur { color: var(--muted); }
  ul.wf-list { list-style: none; } ul.wf-list li { padding: 0.4rem 0; border-bottom: 1px solid var(--border); font-size: 0.85rem; }
  ul.wf-list li span.wf-name { color: var(--accent); font-weight: 500; }
  .empty { color: var(--muted); font-style: italic; font-size: 0.85rem; }
</style>
</head>
<body>
<header>
  <h1><span>Astromesh</span> Dashboard</h1>
  <div id="status">Loading...</div>
</header>
<main>
  <div class="card"><h2>Counters</h2><div id="counters" class="counter-grid"><span class="empty">Loading...</span></div></div>
  <div class="card"><h2>Histograms</h2><div id="histograms"><span class="empty">Loading...</span></div></div>
  <div class="card"><h2>Workflows</h2><div id="workflows"><span class="empty">Loading...</span></div></div>
  <div class="card"><h2>Recent Traces</h2><div id="traces"><span class="empty">Loading...</span></div></div>
</main>
<script>
const BASE = window.location.origin;

async function fetchJSON(path) {
  try { const r = await fetch(BASE + path); return r.ok ? await r.json() : null; } catch { return null; }
}

function renderCounters(data) {
  const el = document.getElementById('counters');
  if (!data || !data.counters || Object.keys(data.counters).length === 0) { el.innerHTML = '<span class="empty">No counters yet</span>'; return; }
  el.innerHTML = Object.entries(data.counters).map(([k,v]) => `<div class="counter"><div class="label">${k}</div><div class="value">${v}</div></div>`).join('');
}

function renderHistograms(data) {
  const el = document.getElementById('histograms');
  if (!data || !data.histograms || Object.keys(data.histograms).length === 0) { el.innerHTML = '<span class="empty">No histograms yet</span>'; return; }
  let html = '<table><tr><th>Metric</th><th>Count</th><th>Avg</th><th>Min</th><th>Max</th></tr>';
  for (const [k, v] of Object.entries(data.histograms)) {
    html += `<tr><td>${k}</td><td>${v.count}</td><td>${v.avg?.toFixed(1) ?? '-'}</td><td>${v.min?.toFixed(1) ?? '-'}</td><td>${v.max?.toFixed(1) ?? '-'}</td></tr>`;
  }
  el.innerHTML = html + '</table>';
}

function renderTraces(data) {
  const el = document.getElementById('traces');
  if (!data || !data.traces || data.traces.length === 0) { el.innerHTML = '<span class="empty">No traces yet</span>'; return; }
  let html = '<table><tr><th>Trace ID</th><th>Agent</th><th>Spans</th><th>Status</th></tr>';
  for (const t of data.traces.slice(0, 20)) {
    const ok = (t.spans || []).every(s => s.status !== 'error');
    html += `<tr><td>${t.trace_id?.slice(0,12) ?? '?'}...</td><td>${t.agent ?? '-'}</td><td>${(t.spans||[]).length}</td><td><span class="badge ${ok ? 'badge-ok' : 'badge-err'}">${ok ? 'OK' : 'ERROR'}</span></td></tr>`;
  }
  el.innerHTML = html + '</table>';
}

function renderWorkflows(data) {
  const el = document.getElementById('workflows');
  if (!data || !data.workflows || data.workflows.length === 0) { el.innerHTML = '<span class="empty">No workflows loaded</span>'; return; }
  el.innerHTML = '<ul class="wf-list">' + data.workflows.map(w => `<li><span class="wf-name">${w.name}</span> &mdash; ${w.steps || '?'} steps, trigger: ${w.trigger || 'api'}</li>`).join('') + '</ul>';
}

async function refresh() {
  const [metrics, traces, workflows] = await Promise.all([
    fetchJSON('/v1/metrics/'), fetchJSON('/v1/traces/'), fetchJSON('/v1/workflows')
  ]);
  renderCounters(metrics); renderHistograms(metrics); renderTraces(traces); renderWorkflows(workflows);
  document.getElementById('status').textContent = 'Last updated: ' + new Date().toLocaleTimeString();
}

refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the built-in observability dashboard."""
    return HTMLResponse(content=_DASHBOARD_HTML)
