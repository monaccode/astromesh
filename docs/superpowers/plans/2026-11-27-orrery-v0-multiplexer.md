# Astromesh Orrery v0 — Multiplexer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Rust console app, `orrery`, that runs `claude`, `codex` and shells in real terminal panes
with tabs, a leader key, a status bar, per-project sessions and "needs you" detection, and works on
Windows 11.

**Architecture:** One crate (`lib` + thin `bin`) in `D:\monaccode\astromesh-orrery`. Every pane owns a
PTY (`portable-pty`, ConPTY on Windows) whose output feeds a `vt100` screen; the app state and key
handling are pure and tested without a terminal; a single event loop draws with `ratatui` and routes
keys. Pane events go out on a channel so v1 (MCP pane tools, supervisor) can subscribe without
touching the panes.

**Tech Stack:** Rust stable (1.99 installed; toolchain `x86_64-pc-windows-gnu` on the dev machine),
`ratatui`, `crossterm`, `portable-pty`, `vt100`, `serde` + `toml`, `clap` (derive), `anyhow`,
`regex`, `which`. Add each with `cargo add` (latest release).

**Spec:** `docs/superpowers/specs/2026-11-27-orrery-design.md` (approved 2026-11-27). v0 = §5 phase 1.

## Global Constraints

- Repo `monaccode/astromesh-orrery` (public, Apache-2.0); work on `develop`, conventional commits in
  Spanish like the rest of the ecosystem, each `feat`/`fix` adds its line to `CHANGELOG.md` `[Unreleased]`.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_0193HxycCSWnD33U48X8gr4n`.
- **Platforms: Windows 11, macOS and Linux** (user, 2026-11-27). Windows 11 is the acceptance gate: v0 is not done until Task 9's acceptance passes on Windows with
  `claude` and `codex`. macOS and Linux must build and pass `cargo test` in CI (matrix: windows, ubuntu, macos).
- Orrery never reads, stores or forwards a CLI's credentials. A CLI pane is a PTY and nothing else.
- Sessions live in `<project>/.orrery/session.toml`; "project" = the directory `orrery` was started in.
- Session restore re-launches each pane's command in its cwd; it does not resurrect processes.
- Every pane type is an enum with room for v1: `PaneKind` is `#[non_exhaustive]`, and an `Agent`
  variant is **not** added in v0.
- `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` and `cargo test` pass before every commit.

## Review Focus

1. **Commands that are `.cmd`/`.ps1` shims on Windows** (`codex` is `codex.cmd` from npm): spawning
   `codex` must work, not fail with "file not found". → Task 2 `resolve_command` test.
2. **The leader key reaching a CLI that also uses it**: pressing the leader twice must send it to the
   pane once, and an unknown key after the leader must be dropped, not leaked. → Task 5 tests.
3. **A pane whose process exits** (typing `exit`, a crash, `claude` quitting): the pane stays, shows
   `exited (code)`, and the app does not panic or hang. → Task 3 and Task 6 tests.
4. **A corrupt or older `session.toml`**: start with the default session and print one warning line;
   never refuse to start, never overwrite the bad file without keeping it as `session.toml.bak`. → Task 2 test.
5. **Resizing the terminal**: every PTY gets the new pane size so `claude`/`codex` redraw correctly. →
   Task 4 test on `pane_rects` + Task 7 resize wiring + Task 9 manual check.

---

## File Structure

```
astromesh-orrery/
  Cargo.toml
  src/main.rs        clap CLI → orrery::run
  src/lib.rs         module list, pub fn run(opts) -> anyhow::Result<()>
  src/session.rs     Session / Tab / PaneSpec / PaneKind, load/save, presets, resolve_command
  src/pane.rs        Pane: PTY + vt100 parser + reader thread, PaneEvent channel
  src/detect.rs      PaneState and the "needs you" rule (pure)
  src/layout.rs      pane_rects (pure)
  src/keys.rs        crossterm KeyEvent → PTY bytes (pure)
  src/app.rs         App state, leader-key state machine, Action list (pure)
  src/ui.rs          ratatui drawing: tab bar, panes, status bar
  src/run.rs         terminal setup/teardown, event loop, wiring
  tests/pty.rs       real-PTY integration tests (Windows + Linux)
  docs/v0-acceptance.md
  .github/workflows/ci.yml
```

---

### Task 1: Crate scaffold and CI

**Files:**
- Create: `Cargo.toml`, `src/main.rs`, `src/lib.rs`, `.github/workflows/ci.yml`, `rust-toolchain.toml`
- Modify: `CHANGELOG.md`, `.gitignore` (already ignores `/target`, `.orrery/`)

**Interfaces:**
- Produces: package/binary name `orrery`, version `0.0.1`, edition 2024;
  `pub struct RunOptions { pub project_dir: std::path::PathBuf }` and
  `pub fn run(opts: RunOptions) -> anyhow::Result<()>` in `src/lib.rs` (body: `todo!` replaced in Task 7).

- [ ] **Step 1:** `cargo init --name orrery` in the repo root; `rust-toolchain.toml` with `channel = "stable"`, components `rustfmt`, `clippy`.
- [ ] **Step 2:** `src/main.rs`: clap derive `Cli { #[arg(long, short = 'C')] dir: Option<PathBuf> }`, `--version` from Cargo; calls `orrery::run(RunOptions { project_dir: dir or current_dir })`.
- [ ] **Step 3:** CI: on push to `main`/`develop` and PRs, `concurrency` with `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}`, `paths-ignore: ["**.md", "docs/**", "assets/**"]`, matrix `windows-latest` + `ubuntu-latest`, steps fmt check, clippy `-D warnings`, `cargo test`, `Swatinem/rust-cache`.
- [ ] **Step 4:** Run `cargo build && cargo run -- --version`. Expected: `orrery 0.0.1`.
- [ ] **Step 5:** CHANGELOG `### Added` line; commit `chore: scaffold del crate orrery y CI`.

### Task 2: Session model, presets and command resolution

**Files:**
- Create: `src/session.rs`
- Test: unit tests in `src/session.rs`

**Interfaces:**
- Produces:
  ```rust
  #[non_exhaustive] #[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
  #[serde(rename_all = "lowercase")]
  pub enum PaneKind { Claude, Codex, Shell, Command }
  pub struct PaneSpec { pub kind: PaneKind, pub command: Option<String>, pub args: Vec<String>,
                        pub cwd: Option<PathBuf>, pub label: Option<String> }
  #[serde(rename_all = "lowercase")] pub enum Split { Vertical, Horizontal }   // Vertical = side by side
  pub struct Tab { pub name: String, pub split: Split, pub panes: Vec<PaneSpec> }
  pub struct Session { pub version: u32, pub leader: String, pub idle_ms: u64, pub tabs: Vec<Tab> }
  impl Session {
      pub fn default_for(project: &Path) -> Session;           // version 1, leader "ctrl+space", idle_ms 1500, one tab "main" with one Shell pane
      pub fn load(project: &Path) -> (Session, Option<String>); // (session, warning)
      pub fn save(&self, project: &Path) -> anyhow::Result<()>; // writes .orrery/session.toml, creates dir
  }
  pub struct Launch { pub program: PathBuf, pub args: Vec<String>, pub cwd: PathBuf }
  pub fn launch_for(spec: &PaneSpec, project: &Path) -> anyhow::Result<Launch>;
  pub fn resolve_command(name: &str) -> anyhow::Result<PathBuf>;
  ```
- Preset programs: `Claude` → `claude`, `Codex` → `codex`, `Shell` → on Windows `pwsh` if found else
  `powershell.exe`, elsewhere `$SHELL` else `/bin/sh`; `Command` → `spec.command` (error if `None`).
- `resolve_command` uses the `which` crate (honors `PATHEXT`). A resolved `.cmd`/`.bat` becomes
  program `cmd.exe` with args `["/c", <resolved path>, ...]`; `.ps1` becomes `powershell.exe -NoLogo -File <path>`.
- `cwd` relative paths resolve against the project dir; `None` → project dir.

- [ ] **Step 1: Tests** —
  `default_session_has_one_shell_tab` (1 tab named `main`, 1 pane `Shell`, leader `ctrl+space`, idle_ms 1500);
  `save_then_load_roundtrips` (tempdir; two tabs, mixed kinds; `load` returns equal session and `None` warning);
  `missing_file_gives_default_without_warning`;
  `corrupt_file_gives_default_warning_and_backup` (write `not = [valid`; `load` → default, warning contains `session.toml`, and `.orrery/session.toml.bak` exists with the original bytes);
  `newer_version_is_treated_as_corrupt` (`version = 99` → default + warning);
  `command_kind_without_command_is_error`;
  `relative_cwd_resolves_against_project`;
  `#[cfg(windows)] cmd_shim_runs_through_cmd_exe` (create `tmp/fake.cmd`, prepend tmp to PATH for the test, `launch_for(Command "fake")` → program ends with `cmd.exe`, args[0] == `/c`).
- [ ] **Step 2:** `cargo test session` — FAIL (unresolved).
- [ ] **Step 3:** Implement per Interfaces. Use `tempfile` as a dev-dependency.
- [ ] **Step 4:** `cargo test session` — PASS.
- [ ] **Step 5:** CHANGELOG; commit `feat: sesiones por proyecto y presets de paneles`.

### Task 3: Pane — PTY, screen and events

**Files:**
- Create: `src/pane.rs`, `tests/pty.rs`

**Interfaces:**
- Consumes: `Launch` (Task 2).
- Produces:
  ```rust
  pub type PaneId = u64;
  #[derive(Debug, Clone, PartialEq)]
  pub enum PaneEvent { Output(PaneId), Exited(PaneId, Option<u32>) }
  pub struct Pane { pub id: PaneId, pub spec: PaneSpec, /* private: parser, writer, master, child */ }
  impl Pane {
      pub fn spawn(id: PaneId, spec: PaneSpec, launch: &Launch, rows: u16, cols: u16,
                   events: std::sync::mpsc::Sender<PaneEvent>) -> anyhow::Result<Pane>;
      pub fn write(&mut self, bytes: &[u8]) -> anyhow::Result<()>;
      pub fn resize(&mut self, rows: u16, cols: u16) -> anyhow::Result<()>;   // PTY and vt100 parser
      pub fn screen(&self) -> std::sync::MutexGuard<'_, vt100::Parser>;
      pub fn screen_text(&self) -> String;          // parser.screen().contents()
      pub fn last_output(&self) -> std::time::Instant;
      pub fn exit_code(&self) -> Option<Option<u32>>; // None = running; Some(code) = exited
      pub fn kill(&mut self);
  }
  ```
- A reader thread per pane: read PTY → `parser.process` → update `last_output` → send `Output(id)`
  (drop send errors). On EOF it waits the child and sends `Exited(id, code)`. vt100 scrollback 2000 lines.
- This is the seam v1 uses (`read_pane` = `screen_text`, `send_to_pane` = `write`, `wait_pane` = events).

- [ ] **Step 1: Tests in `tests/pty.rs`** (helper `echo_launch(text)` → Windows `cmd.exe /c echo <text>`, else `/bin/sh -c "echo <text>"`; helper `wait_for(pane, pred, 5s)`):
  `spawned_command_output_reaches_screen` (`echo orrery-ok` → `screen_text()` contains `orrery-ok`);
  `exit_is_reported` (receives `PaneEvent::Exited(id, Some(0))` within 5 s; `exit_code()` == `Some(Some(0))`);
  `write_reaches_interactive_shell` (spawn the Shell preset, write `echo typed-ok\r`, screen contains `typed-ok`);
  `resize_changes_screen_size` (after `resize(30, 100)`, `screen().screen().size() == (30, 100)`).
- [ ] **Step 2:** `cargo test --test pty` — FAIL.
- [ ] **Step 3:** Implement with `portable_pty::native_pty_system()`; `CommandBuilder` from `Launch` with `cwd`; set `TERM=xterm-256color`.
- [ ] **Step 4:** `cargo test --test pty` — PASS on Windows (and Linux in CI).
- [ ] **Step 5:** CHANGELOG; commit `feat: paneles PTY con pantalla vt100 y eventos`.

### Task 4: Pure pieces — layout, key encoding, "needs you"

**Files:**
- Create: `src/layout.rs`, `src/keys.rs`, `src/detect.rs` (unit tests in each)

**Interfaces:**
- Produces:
  ```rust
  // layout.rs — equal split, remainder to the last pane, area = space between tab bar and status bar
  pub fn pane_rects(area: ratatui::layout::Rect, n: usize, split: Split) -> Vec<Rect>;
  pub fn inner(rect: Rect) -> Rect;   // minus 1-cell border; PTY size = inner(rect).height/width
  // keys.rs
  pub fn encode_key(key: crossterm::event::KeyEvent) -> Option<Vec<u8>>;
  // detect.rs
  #[derive(Debug, Clone, Copy, PartialEq)]
  pub enum PaneState { Running, NeedsYou, Exited(Option<u32>) }
  pub struct Activity { pub last_output: Instant, pub last_input: Option<Instant>,
                        pub had_output_since_input: bool, pub exit_code: Option<Option<u32>> }
  pub fn pane_state(a: &Activity, now: Instant, idle_ms: u64) -> PaneState;
  ```
- `pane_state` rule: exited → `Exited`; else `NeedsYou` when `had_output_since_input` and
  `now - last_output >= idle_ms` and (no input yet, or `last_output > last_input`); else `Running`.
  (A pane that went quiet after answering you needs you; one you just typed into and that has not
  answered is still working.)

- [ ] **Step 1: Tests** —
  layout: `one_pane_fills_area`; `vertical_split_three_columns_cover_area_without_gaps` (area 100×40, widths 33,33,34, x contiguous); `horizontal_split_rows`; `zero_panes_is_empty`; `inner_shrinks_by_border` (10×5 → 8×3, and never underflows on 1×1).
  keys: `a`→`b"a"`; `Enter`→`b"\r"`; `Ctrl+C`→`[0x03]`; `Up`→`b"\x1b[A"`; `Backspace`→`[0x7f]`; `Tab`→`b"\t"`; `BackTab`→`b"\x1b[Z"`; `Esc`→`[0x1b]`; `Alt+x`→`b"\x1bx"`; `F1`→`b"\x1bOP"`; `Delete`→`b"\x1b[3~"`; `Home`/`End`→`b"\x1b[H"`/`b"\x1b[F"`; `PageUp`→`b"\x1b[5~"`; a key-release event → `None`; `'ñ'` → its UTF-8 bytes.
  detect: `exited_wins`; `quiet_after_output_needs_you` (idle 1500, 2000 ms quiet → NeedsYou); `recent_output_is_running` (500 ms → Running); `just_typed_no_answer_is_running`; `no_output_ever_is_running`.
- [ ] **Step 2:** `cargo test layout keys detect` — FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** CHANGELOG; commit `feat: layout, codificación de teclas y detección de "te necesita"`.

### Task 5: App state and leader key

**Files:**
- Create: `src/app.rs` (unit tests)

**Interfaces:**
- Consumes: `Session`, `PaneSpec`, `PaneKind`, `PaneId`, `PaneState`, `encode_key`.
- Produces:
  ```rust
  pub struct TabState { pub name: String, pub split: Split, pub panes: Vec<PaneId>, pub focus: usize }
  pub struct App { pub tabs: Vec<TabState>, pub active: usize, pub mode: Mode, pub leader: KeyEvent /* parsed */ }
  pub enum Mode { Normal, Leader, PickKind }
  #[derive(Debug, PartialEq)]
  pub enum Action { Send(PaneId, Vec<u8>), Spawn { tab: usize, kind: PaneKind }, Close(PaneId),
                    NewTab, Save, Quit, Redraw }
  pub fn parse_leader(s: &str) -> anyhow::Result<KeyEvent>;   // "ctrl+space", "ctrl+a", "ctrl+\\", "ctrl+g"
  impl App {
      pub fn new(leader: KeyEvent) -> App;
      pub fn focused(&self) -> Option<PaneId>;
      pub fn add_pane(&mut self, tab: usize, id: PaneId);   // focuses it
      pub fn remove_pane(&mut self, id: PaneId);             // fixes focus; empty tab is removed unless it is the last
      pub fn handle_key(&mut self, key: KeyEvent, states: &dyn Fn(PaneId) -> PaneState) -> Vec<Action>;
  }
  ```
- Bindings after the leader: `n` → `PickKind` mode, then `1` Claude / `2` Codex / `3` Shell → `Spawn` (Esc cancels);
  `x` close focused; `←→↑↓` and `h j k l` move focus within the tab; `t` → `NewTab`; `1`–`9` go to tab;
  `]`/`[` next/prev tab; `w` focus the next pane (any tab, wrapping) whose state is `NeedsYou`;
  `s` → `Save`; `q` → `Save` then `Quit`; leader again → `Send(focused, encode(leader))`; any other key → nothing.
  Outside leader mode every key → `Send(focused, encode_key(key))` (nothing if no pane or `None`).
- `NewTab` and the first Shell pane in it are spawned by the loop (Task 7), not here.

- [ ] **Step 1: Tests** — `normal_keys_go_to_focused_pane`; `leader_then_unknown_key_is_swallowed`; `double_leader_sends_leader_once`; `leader_n_2_spawns_codex_in_active_tab`; `pick_kind_esc_cancels`; `focus_moves_and_clamps` (3 panes, `l` three times stays on last); `w_jumps_to_needs_you_across_tabs`; `w_with_none_waiting_does_nothing`; `q_saves_then_quits` (exact `vec![Save, Quit]`); `remove_last_pane_keeps_empty_tab_and_focus_none`; `parse_leader_accepts_ctrl_space_and_rejects_garbage`.
- [ ] **Step 2:** `cargo test app` — FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** CHANGELOG; commit `feat: estado de la app y tecla líder`.

### Task 6: Drawing

**Files:**
- Create: `src/ui.rs` (tests with `ratatui::backend::TestBackend`)

**Interfaces:**
- Consumes: `App`, `pane_rects`, `inner`, `PaneState`, `vt100::Screen`.
- Produces:
  ```rust
  pub struct PaneView<'a> { pub id: PaneId, pub title: String, pub state: PaneState, pub screen: &'a vt100::Screen }
  pub fn draw(f: &mut ratatui::Frame, app: &App, views: &[PaneView]);
  pub fn render_screen(screen: &vt100::Screen, area: Rect, buf: &mut ratatui::buffer::Buffer);
  ```
- Layout: row 0 tab bar (`1:main  2:review`, active highlighted, a `◆` after a tab with a NeedsYou pane);
  panes in between with a border whose title is `label-or-kind · state` where state is `running`,
  `◆ needs you` or `exited (N)`; focused border in amber `#f5a623`, others dim; last row status bar:
  `<leader> n new · x close · w next waiting · q quit` on the left, `N waiting` on the right when N > 0,
  and `LEADER`/`NEW: 1 claude 2 codex 3 shell` while in those modes.
- `render_screen` copies cells: char, fg/bg (vt100 `Color::Idx`/`Rgb` → ratatui), bold/italic/underline/inverse;
  draws the cursor of the focused pane via `f.set_cursor_position` when the screen does not hide it.

- [ ] **Step 1: Tests** — `pane_text_is_drawn` (vt100 parser fed `hello`, buffer row inside the pane contains `hello`); `title_shows_needs_you`; `exited_title_shows_code` (`exited (1)`); `status_bar_counts_waiting` (`2 waiting`); `leader_mode_shown_in_status_bar`; `colors_are_copied` (feed `\x1b[31mR`, cell fg is red).
- [ ] **Step 2:** `cargo test ui` — FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** CHANGELOG; commit `feat: dibujo de pestañas, paneles y barra de estado`.

### Task 7: Event loop, session restore and wiring

**Files:**
- Create: `src/run.rs`; Modify: `src/lib.rs` (`run`)

**Interfaces:**
- Consumes: everything above.
- Produces: `pub fn run(opts: RunOptions) -> anyhow::Result<()>` that:
  1. `Session::load`; prints the warning (if any) to stderr before entering the alternate screen.
  2. Enables raw mode, alternate screen, `crossterm` keyboard enhancement flags when supported; a
     guard restores the terminal on every exit path, panics included (`std::panic::set_hook` + `Drop`).
  3. Spawns every pane of every tab with its rect's inner size; a pane that fails to spawn becomes a
     pane in `Exited(None)` whose screen shows the error text — the app still starts.
  4. Loop: drain `PaneEvent`s; `crossterm::event::poll(16ms)`; key → `app.handle_key` → apply actions;
     `Event::Resize` → recompute rects and `resize` every pane; redraw when anything changed.
     Track `last_input` per pane when sending keys, for `pane_state`.
  5. `Save` writes the current tabs/panes back to `Session` (specs, not processes); `Quit` kills all
     panes and returns.
- Keep `run.rs` thin: all decisions already live in `app`, `detect`, `layout`, `ui`.

- [ ] **Step 1: Test** — `session_from_app_roundtrip` (pure helper `fn session_from(app: &App, specs: &HashMap<PaneId, PaneSpec>, base: &Session) -> Session`: two tabs → equal tab/pane order and kinds).
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** `cargo test` all PASS; `cargo clippy --all-targets -- -D warnings` clean.
- [ ] **Step 5: Smoke (Windows):** `cargo run` in a temp dir → one shell pane, `dir` works; leader `n 3` opens a second shell side by side; leader `q` exits and `.orrery/session.toml` has 2 panes; `cargo run` again restores both.
- [ ] **Step 6:** CHANGELOG; commit `feat: loop principal y restauración de sesiones`.

### Task 8: README, docs and changelog for v0

**Files:**
- Modify: `README.md`, `README.es.md`, `CHANGELOG.md`; Create: `docs/usage.md`

- [ ] **Step 1:** `docs/usage.md` (English): install from source (`cargo install --git https://github.com/monaccode/astromesh-orrery --branch develop`), `orrery` / `orrery -C <dir>`, every binding from Task 5, `session.toml` fields with an example, what "needs you" means and that `idle_ms` tunes it.
- [ ] **Step 2:** READMEs: status line becomes "v0 in progress: multiplexer, build from source"; add a short Usage section linking `docs/usage.md`. Spanish README mirrors it.
- [ ] **Step 3:** Commit `docs: uso de la v0`.

### Task 9: Windows acceptance (the gate)

**Files:**
- Create: `docs/v0-acceptance.md` (checklist + results table with date and versions of `claude`, `codex`, Windows build)

- [ ] **Step 1:** Write the checklist. Each line is pass/fail, on Windows 11 in Windows Terminal:
  1. `claude` pane starts, its UI renders with colors, typing and Enter work, `Esc` and `Ctrl+C` reach it.
  2. `codex` pane (npm `.cmd` shim) starts and the same keys work.
  3. Resize the window: both redraw at the new size, no garbage lines.
  4. Leader twice sends the leader to `claude`; leader + unknown key sends nothing.
  5. Ask `claude` something; while it works the pane shows `running`; when it waits for you it shows `◆ needs you` within ~2 s and the status bar counts it; leader `w` jumps to it.
  6. `/exit` in `claude`: pane shows `exited (0)`; leader `x` closes it.
  7. Quit and restart: tabs, panes, labels and cwd come back.
  8. Corrupt `session.toml` by hand: Orrery starts with the default, warns once, keeps `.bak`.
- [ ] **Step 2:** Run it (the human runs `claude`/`codex` with their own logins; the agent never handles credentials). Fix what fails with a test where the cause is in pure code, then re-run the failing lines.
- [ ] **Step 3:** Record results; commit `docs: aceptación de la v0 en Windows`. v0 is done only when every line passes.
