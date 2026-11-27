# Astromesh Orrery v1 — Astromesh Inside Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Native Astromesh agents run inside Orrery panes, read/edit/run in the project and see/drive the
other panes through an Orrery MCP server, with every write gated by a human confirmation; a supervisor
agent splits a task between a CLI pane and a native agent.

**Architecture:** Three small core changes make the runtime usable from a local client (`confirm` on
`type: mcp` tools so write tools execute behind the gate, `connections` + `pendiente` on the WebSocket,
opt-in loopback for MCP). Orrery gains a localhost MCP server (streamable HTTP, bearer token) with
workspace and pane tools, a runtime link that starts or finds the runtime and registers Orrery's bundled
agents, and a new pane kind that is a chat view over `WS /v1/ws/agent/{name}`.

**Tech Stack:** Core: Python 3.12, FastAPI, pydantic, pytest (`uv`). Orrery: Rust (1.88+), `tokio`
(one background runtime thread), `rmcp` (official MCP Rust SDK, streamable-HTTP server), `axum`,
`tungstenite` (blocking WS client on its own thread), `ureq` (blocking HTTP), `serde_json`, `serde_yaml`.

**Spec:** `docs/superpowers/specs/2026-11-27-orrery-design.md` §4.2–4.5, §5 phase 2, §7 (approved 2026-11-27).

## Global Constraints

- Two repos. **Core:** `D:\monaccode\astromesh`, branch `feature/orrery-v1-core` from `develop`; CLAUDE.md
  rules apply (CHANGELOG `[Unreleased]` before every `feat`/`fix`, `ruff check` + `ruff format --check`).
  **Orrery:** `D:\monaccode\astromesh-orrery`, work on `develop`; `cargo fmt --check`, `clippy -D warnings`,
  `cargo test` before every commit; CHANGELOG `[Unreleased]`.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_0193HxycCSWnD33U48X8gr4n`. Conventional commits in Spanish.
- Never push, tag or publish to PyPI without the user's OK. The core release (0.76.0) is out of this plan.
- Orrery never uses a CLI's credentials. Native agents use the core's providers (API keys / local models).
- The MCP server binds `127.0.0.1` only, ephemeral port, random 32-byte token per start; every request
  without `Authorization: Bearer <token>` gets 401.
- Workspace root = the project dir. Any path that resolves (after `..` and symlinks) outside it is
  rejected with an error the model sees. `run_command` runs only with cwd inside the root.
- Write tools (`write_file`, `edit_file`, `run_command`, `send_to_pane`, `spawn_pane`) are always listed in
  the agent's `confirm`; a gated call never runs before a human `origen: humano` confirmation.
- Loopback for MCP is allowed only when `ASTROMESH_MCP_ALLOW_LOOPBACK=1` and only for `127.0.0.1`/`::1`;
  everything else keeps the existing public-host pinning.
- Platforms: Windows 11, macOS, Linux; `#[cfg(unix)]`/`#[cfg(windows)]` only.

## Review Focus

1. **Path escape** (`../x`, absolute paths, a symlink inside the root pointing out, `C:\` vs `c:\`, UNC):
   rejected, never read or written. → Task 4 tests.
2. **A confirmation the model never re-issues / a different call after "si"**: nothing runs; the pending
   slot is dropped as the core does today. → Task 1 test + Task 7 shows the pending bar until `done`.
3. **Runtime not installed / port taken / runtime crashes mid-session**: the agent pane shows the error
   and the rest of Orrery keeps working; CLI panes are unaffected. → Task 6 tests.
4. **`run_command` that never ends or floods output**: killed at `timeout_ms` (default 60000), output
   capped at 64 KiB with a truncation note. → Task 4 tests.
5. **`send_to_pane` to an exited or unknown pane, `wait_pane` that never matches**: an error result /
   `timed_out: true`, never a hang of the MCP server. → Task 5 tests.

---

## File Structure

```
astromesh (core)
  astromesh/runtime/engine.py           confirm on type: mcp (Task 1)
  astromesh/integrations/mcp.py         writes:true allowed when listed in confirm (Task 1)
  astromesh/api/ws.py                   connections + pendiente (Task 2)
  astromesh/tools/builtin/_red.py       opt-in loopback (Task 3)
  tests/test_mcp_confirm.py, tests/test_ws_connections.py, tests/test_red_loopback.py
astromesh-orrery
  src/mcp/mod.rs        server start/stop, token, tool registry (Task 4)
  src/mcp/workspace.rs  root confinement + workspace tools (Task 4)
  src/mcp/panes.rs      pane tools over a PaneBridge channel (Task 5)
  src/runtime.rs        [astromesh] config, start/find runtime, register agents (Task 6)
  src/agents/*.yaml     orrery-coder, orrery-reviewer, orrery-supervisor manifests (Task 6)
  src/agent_pane.rs     WS client + transcript model + input line + pending bar (Task 7)
  src/session.rs, app.rs, ui.rs, run.rs   PaneKind::Agent, picker, wiring (Task 7)
  docs/v1-acceptance.md (Task 8)
```

---

### Task 1 (core): `confirm` applies to `type: mcp`, write tools execute behind the gate

**Files:** Modify `astromesh/runtime/engine.py` (warning at ~1076, mcp branch ~1261-1290),
`astromesh/integrations/mcp.py` (`_ToolMcp._escribe_solo_proponiendo`); Test `tests/test_mcp_confirm.py`.

**Interfaces:**
- Produces: in an agent YAML, a `type: mcp` entry may carry `confirm: [<tool name as declared in tools[]>, ...]`.
  A tool with `writes: true` is valid if `mode: propose` (unchanged) **or** its name is in `confirm`
  (mode omitted) — then it calls the server, with `needs_confirmation=True`. A name in `confirm` that is
  not in `tools[]` is a load error naming it. `writes: true` without propose and not in `confirm` stays an error.

- [ ] **Step 1: Tests** — `test_write_tool_in_confirm_loads_and_needs_confirmation`;
  `test_write_tool_not_in_confirm_without_propose_is_error`; `test_confirm_unknown_tool_is_error`;
  `test_gated_mcp_call_rejected_then_runs_after_human_si` (mock MCP via the module's transport seam: first
  call returns `confirmacion_requerida`, follow-up turn `"si"` with `origen: humano` lets the identical call
  reach the server once); `test_agent_origin_cannot_confirm_mcp_call`; `test_propose_mode_unchanged`.
- [ ] **Step 2:** `uv run pytest tests/test_mcp_confirm.py -v` — FAIL.
- [ ] **Step 3:** Implement. `_ServidorMcp` forbids extra keys: pass `confirm` through the engine (it is in
  `_CLAVES_COMUNES`) and validate the writes/propose rule against it there or by giving the model the set.
- [ ] **Step 4:** PASS; full `uv run pytest -q`; ruff check + format --check.
- [ ] **Step 5:** CHANGELOG `### Added`; commit `feat(mcp): confirm en tools mcp, las de escritura corren tras la compuerta`.

### Task 2 (core): WebSocket carries `connections` and reports the pending confirmation

**Files:** Modify `astromesh/api/ws.py`, the run path it calls; Test `tests/test_ws_connections.py`.

**Interfaces:**
- Produces: client message `{"query", "origen"?, "connections"?}` — `connections` validated exactly like
  `AgentRunRequest.connections` and passed to the run (never logged, traced or echoed).
  `done` gains `"pendiente": {"tool": str, "argumentos": dict} | null` — the session's pending gated call
  after this turn, `null` when none.

- [ ] **Step 1: Tests** — `test_ws_connections_reach_the_run`; `test_ws_connections_not_echoed_or_traced`;
  `test_done_has_pendiente_after_gated_call` (tool + argumentos); `test_done_pendiente_null_after_confirmed_run`;
  `test_ws_invalid_connections_is_error_without_run`.
- [ ] **Steps 2–4:** FAIL → implement → PASS + full suite + ruff.
- [ ] **Step 5:** CHANGELOG; commit `feat(ws): connections por mensaje y pendiente en done`.

### Task 3 (core): opt-in loopback for MCP

**Files:** Modify `astromesh/tools/builtin/_red.py` (and its call in `integrations/mcp.py` only);
Test `tests/test_red_loopback.py`.

**Interfaces:**
- Produces: `TransportePineado(..., permitir_loopback: bool = False)`; the MCP client passes
  `permitir_loopback=os.environ.get("ASTROMESH_MCP_ALLOW_LOOPBACK") == "1"`. With it, `127.0.0.1` and `::1`
  are allowed; every other private range stays blocked. Integrations (`executor.py`) never pass it.

- [ ] **Step 1: Tests** — `test_loopback_blocked_by_default`; `test_loopback_allowed_with_flag` (127.0.0.1 and ::1);
  `test_private_ranges_still_blocked_with_flag` (10.0.0.1, 192.168.1.1, 169.254.169.254);
  `test_localhost_name_resolving_to_loopback_allowed_with_flag`; `test_integrations_never_get_loopback`.
- [ ] **Steps 2–4:** FAIL → implement → PASS + full suite + ruff.
- [ ] **Step 5:** CHANGELOG `### Added` (mention it exists for local clients such as Orrery); commit
  `feat(red): loopback opcional para servidores MCP locales`.

### Task 4 (Orrery): MCP server with workspace tools

**Files:** Create `src/mcp/mod.rs`, `src/mcp/workspace.rs`; Modify `src/lib.rs`, `Cargo.toml`; Test unit tests + `tests/mcp_http.rs`.

**Interfaces:**
- Produces:
  ```rust
  pub struct McpServer { pub port: u16, pub token: String, /* private: shutdown, thread */ }
  impl McpServer {
      pub fn start(root: PathBuf) -> anyhow::Result<McpServer>; // 127.0.0.1:0 (Task 5 adds the pane bridge)
      pub fn url(&self) -> String;                       // "http://127.0.0.1:<port>/mcp"
  }
  impl Drop for McpServer { /* stops the server */ }
  pub struct ToolInfo { pub name: &'static str, pub description: &'static str,
                        pub input_schema: serde_json::Value, pub writes: bool }
  pub fn tool_catalog(with_panes: bool) -> Vec<ToolInfo>;   // single source for the YAML manifests (Task 6)
  // workspace.rs
  pub fn confine(root: &Path, requested: &str) -> Result<PathBuf, String>;
  ```
- Tools (names exact): `read_file {path, offset?, limit?}` (text, max 256 KiB), `write_file {path, content}`,
  `edit_file {path, old, new}` (exactly one occurrence of `old`, else error saying how many),
  `list_files {path?, glob?}` (respects `.gitignore` via the `ignore` crate, max 2000 entries),
  `grep {pattern, path?, glob?}` (regex, max 500 matches), `run_command {command, cwd?, timeout_ms?}`
  (Windows `cmd /c`, unix `sh -c`; default timeout 60000; stdout+stderr capped at 64 KiB with
  `[truncated]`; returns `{exit_code, output, timed_out}`). `writes = true` for write_file, edit_file, run_command.
- `confine` canonicalizes the root and the deepest existing ancestor of the requested path; rejects when
  the result is not under the root (component-wise, case-insensitive on Windows).

- [ ] **Step 1: Tests** — confine: `dotdot_escape_rejected`, `absolute_outside_rejected`,
  `symlink_out_of_root_rejected` (`#[cfg(unix)]` symlink; `#[cfg(windows)]` junction or skip with reason),
  `new_file_inside_allowed`, `prefix_sibling_rejected` (root `/a/b`, path `/a/bc/x`), `windows_case_insensitive`;
  tools: `edit_file_requires_single_occurrence`, `run_command_times_out` (sleep 5 s with timeout 500 → `timed_out: true`),
  `run_command_output_capped`, `list_files_respects_gitignore`;
  HTTP (`tests/mcp_http.rs`): `no_token_is_401`, `wrong_token_is_401`, `lists_tools_and_calls_read_file`
  (real MCP client from `rmcp`), `binds_loopback_only` (`url()` host is `127.0.0.1`).
- [ ] **Steps 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** CHANGELOG; commit `feat: servidor MCP local con tools de workspace`.

### Task 5 (Orrery): pane tools

**Files:** Create `src/mcp/panes.rs`; Modify `src/mcp/mod.rs` (signature becomes `start(root: PathBuf, panes: Option<PaneBridge>)`; pane tools registered only with `Some`), `src/run.rs` (serve bridge requests each loop tick).

**Interfaces:**
- Produces:
  ```rust
  pub enum PaneOp { List, Read { id: PaneId, lines: usize }, Send { id: PaneId, text: String },
                    Spawn { kind: PaneKind, agent: Option<String> },
                    Wait { id: PaneId, until: WaitUntil, timeout_ms: u64 } }
  pub enum WaitUntil { Regex(String), IdleMs(u64), Exit, Waiting }
  pub struct PaneRequest { pub op: PaneOp, pub reply: std::sync::mpsc::Sender<serde_json::Value> }
  #[derive(Clone)] pub struct PaneBridge(pub std::sync::mpsc::Sender<PaneRequest>);
  ```
  Tools: `list_panes {}` → `[{id, kind, label, state}]`; `read_pane {id, lines?=60}` → last N screen lines;
  `send_to_pane {id, text}` (text sent as typed; `\n` → Enter); `spawn_pane {kind, agent?}` → `{id}`;
  `wait_pane {id, until: {regex|idle_ms|exit|waiting}, timeout_ms?=120000}` → `{matched, timed_out, state}`.
  `send_to_pane` and `spawn_pane` are writes. The loop answers `Wait` by polling each tick, never blocking it.

- [ ] **Step 1: Tests** (bridge served by a fake loop in the test) — `send_to_unknown_pane_is_error`,
  `send_to_exited_pane_is_error`, `wait_times_out_with_flag`, `wait_regex_matches`, `read_pane_last_lines`,
  `loop_never_blocks_on_wait` (two concurrent waits + a list answered immediately).
- [ ] **Steps 2–4:** FAIL → implement → PASS (incl. existing e2e).
- [ ] **Step 5:** CHANGELOG; commit `feat: tools de paneles por MCP`.

### Task 6 (Orrery): runtime link and bundled agents

**Files:** Create `src/runtime.rs`, `src/agents/orrery-coder.agent.yaml`, `orrery-reviewer.agent.yaml`,
`orrery-supervisor.agent.yaml`; Modify `src/session.rs` (`[astromesh]` section).

**Interfaces:**
- Produces:
  ```rust
  #[serde(default)] pub struct AstromeshConfig { pub url: Option<String>,            // use a running runtime
      pub core: String,             // default "astromesh[mcp]==0.76.0"; a path or spec for `uvx --from`
      pub model_provider: String, pub model_name: String }   // injected into the manifests
  pub struct Runtime { pub base_url: String /* private: child */ }
  impl Runtime {
      pub fn connect(cfg: &AstromeshConfig, project: &Path) -> anyhow::Result<Runtime>;
      pub fn register_agents(&self, mcp: &McpServer, cfg: &AstromeshConfig) -> anyhow::Result<Vec<String>>;
      pub fn connections(&self, mcp: &McpServer) -> serde_json::Value;  // per-run, never persisted
  }
  pub fn manifest(name: &str, cfg: &AstromeshConfig) -> anyhow::Result<serde_json::Value>; // pure
  ```
- `connect`: `cfg.url` (or env `ASTROMESH_URL`) → use it; else spawn
  `uvx --from <core> uvicorn astromesh.api.main:app --host 127.0.0.1 --port <free>` with env
  `ASTROMESH_MCP_ALLOW_LOOPBACK=1`, `ASTROMESH_LOG_LEVEL=WARNING`, stdout/stderr to `.orrery/astromesh.log`;
  ready when `GET /v1/agents` is 200 within 60 s, else error with the log tail. The child is killed on drop.
- Manifests: YAML files with one `type: mcp` tool entry `name: orrery`, `connection: orrery`, `path: /mcp`,
  `auth: {scheme: bearer}`; its `tools[]` generated from `tool_catalog` (coder: workspace; reviewer:
  `read_file`, `list_files`, `grep`, `run_command`; supervisor: panes + `read_file`, `grep`); `confirm` lists
  every `writes` tool; model from cfg. `register_agents` POSTs each, PUT on 409.
- `connections()` returns the shape `AgentRunRequest.connections` expects (read `integrations/credentials.py`)
  for connection `orrery` → `{base_url: "http://127.0.0.1:<port>", credential: <token>}`.

- [ ] **Step 1: Tests** — `manifest_lists_catalog_tools_and_confirms_all_writes` (for each of the 3 agents);
  `manifest_injects_model`; `url_config_skips_spawn` (a stub HTTP server from `tiny_http` answers `/v1/agents`);
  `missing_uvx_gives_clear_error` (PATH without uvx); `register_put_on_409` (stub server);
  `#[ignore] registers_on_real_core` (needs local core + uv: `ORRERY_CORE=D:\monaccode\astromesh` → 201s).
- [ ] **Steps 2–4:** FAIL → implement → PASS; run the ignored test once against the Task 1–3 core branch
  (`core = "D:\\monaccode\\astromesh[mcp]"`) and record the result in the report.
- [ ] **Step 5:** CHANGELOG; commit `feat: enlace con el runtime de Astromesh y agentes de Orrery`.

### Task 7 (Orrery): agent panes

**Files:** Create `src/agent_pane.rs`; Modify `src/session.rs` (`PaneKind::Agent`, `PaneSpec.agent:
Option<String>` with serde default), `src/app.rs` (`n 4` → `PickAgent`: `1` coder, `2` reviewer,
`3` supervisor), `src/ui.rs` (draw agent panes), `src/run.rs` (start MCP server + runtime lazily on the
first agent pane; wire events).

**Interfaces:**
- Produces:
  ```rust
  pub enum Line { User(String), Assistant(String), ToolCall { name: String, args: String },
                  ToolResult { ok: bool }, Pending { tool: String, args: String }, Error(String) }
  pub struct Transcript { pub lines: Vec<Line>, pub busy: bool, pub pending: Option<(String, String)> }
  impl Transcript { pub fn apply(&mut self, event: &serde_json::Value); }   // pure: status/token/tool_call/tool_result/done/error
  pub struct AgentPane { /* ws thread, transcript, input line */ }
  impl AgentPane {
      pub fn open(id: PaneId, agent: &str, runtime: &Runtime, mcp: &McpServer, session_id: String,
                  events: Sender<PaneEvent>) -> anyhow::Result<AgentPane>;
      pub fn key(&mut self, key: KeyEvent);    // edit input; Enter sends; with pending: y → "si", n → "no"
      pub fn state(&self) -> PaneState;        // busy → Running; pending or idle after done → NeedsYou
      pub fn screen_text(&self) -> String;     // plain transcript, for read_pane
  }
  ```
- Every message sent is `{"query", "origen": "humano", "connections": runtime.connections(mcp)}`;
  `session_id` = `orrery-<pane id>-<start unix secs>`. Tokens append to the current assistant line.
  The pending bar `confirm <tool>(<args>)?  y / n` shows while `pending` is set.
- Leader commands still work over an agent pane; keys go to `AgentPane::key` instead of a PTY.

- [ ] **Step 1: Tests** — transcript: `tokens_join_into_one_assistant_line`, `tool_call_and_result_lines`,
  `done_with_pendiente_sets_pending`, `done_without_pendiente_clears_it`, `error_line_and_not_busy`;
  keys: `enter_sends_query_with_connections` (fake sender), `y_with_pending_sends_si_n_sends_no`,
  `y_without_pending_is_typed`; app: `leader_n_4_2_spawns_reviewer_agent`; ui: `agent_pane_draws_transcript_and_pending_bar`;
  integration: `agent_pane_against_fake_ws` (a `tungstenite` server thread scripting status/token/done).
- [ ] **Steps 2–4:** FAIL → implement → PASS (all suites, e2e included).
- [ ] **Step 5:** CHANGELOG; commit `feat: paneles de agentes Astromesh`.

### Task 8: docs and v1 acceptance (needs the user)

**Files:** Modify `docs/usage.md`, READMEs, `CHANGELOG.md`; Create `docs/v1-acceptance.md`.

- [ ] **Step 1:** Docs: `[astromesh]` section, agent panes, confirmations (`y`/`n`), what each bundled agent
  may do, that native agents need a provider key or a local model, and the loopback flag.
- [ ] **Step 2:** `docs/v1-acceptance.md`: (1) coder pane edits a file only after `y`; `n` leaves it untouched;
  (2) reviewer reads and greps, cannot write; (3) path outside the project is refused; (4) supervisor: "Claude
  implements X in a CLI pane, the reviewer reviews the diff and answers approved/changes", end to end on
  Windows; (5) runtime missing → clear error, CLI panes fine; (6) quit → runtime child gone.
- [ ] **Step 3:** Commit `docs: uso y aceptación de la v1`. **Stop:** running the acceptance needs the user's
  provider key and spend OK (real model). Hand the checklist over.
