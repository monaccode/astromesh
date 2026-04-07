# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [v0.27.0] - 2026-04-07

### Added
- `WebhookEventDispatcher` — classifies Meta webhook events by `change["field"]` before any parsing; extensible via `WebhookEventHandler` protocol (`astromesh/channels/webhook_dispatcher.py`)
- `StatusUpdateHandler` — built-in handler for WhatsApp delivery/read/failed receipts; emits a `system` SSE event per status update, never routes to the agent
- `DefaultWebhookEventHandler` — fallback for unregistered webhook fields; logs the event and emits a `system` SSE event
- `contact_name: str | None` field on `ChannelMessage` — populated from the Meta `contacts[]` array when available
- `"system"` direction literal on `ChannelEvent` — used for status updates and non-message webhook events surfaced in the Channel Activity panel
- Two-phase dispatch in the per-agent webhook endpoint (`/v1/agents/{name}/channels/whatsapp/webhook`): inspects `change["field"]` before any parsing; user messages are enriched with the sender's WhatsApp display name and routed to the agent; status receipts go to `StatusUpdateHandler`; all other fields go to `WebhookEventDispatcher`
- Contact name passed to `runtime.run()` as `context={"contact_name": ...}` — reference in agent system prompts via `{% if contact_name %}Address the user as {{ contact_name }}.{% endif %}`
- Webhook Event Dispatcher reference documentation with full Meta fields table, custom handler registration guide, and cross-link from the WhatsApp integration guide

### Changed
- `WhatsAppClient.parse_incoming` now accepts a `change["value"]` dict directly instead of the full Meta webhook payload — callers are responsible for iterating `entry[].changes[]` and passing each value

### Fixed
- Per-agent webhook endpoint returns HTTP 400 for non-JSON request bodies (previously returned unhandled 500)
- Channel-level WhatsApp webhook route (`/v1/channels/whatsapp/webhook`) was passing the full Meta payload to `parse_incoming` instead of iterating `entry[].changes[]` — now correctly extracts each `change["value"]`

## [v0.26.0] - 2026-04-07

### Added

- **ChannelEventBus**: thread-safe asyncio event bus (`astromesh/channels/event_bus.py`) that fans out `ChannelEvent` objects to SSE subscribers; ring buffer retains last 100 events for late-joining clients
- **SSE channel events endpoint**: `GET /v1/channels/events?agent=` streams channel traffic as `text/event-stream`; replays buffered events on connect, then streams live; 15 s keepalive pings
- **Incoming event emission**: `receive_agent_message` emits a `direction="in"` `ChannelEvent` for each parsed inbound message before dispatching to the agent
- **Outgoing event emission**: `_process_agent_message` emits a `direction="out"` `ChannelEvent` after a successful `send_text` reply

### Fixed

- **`adapter` unbound in error handler**: added `adapter = None` sentinel before the `try:` block in `_process_agent_message` — prevents `UnboundLocalError` when the adapter was never initialised before an exception
- **Atomic buffer append in EventBus**: moved `self._buffer.append(event)` inside the `self._lock` block to eliminate a race between the buffer write and subscriber fan-out

## [v0.25.0] - 2026-04-07

### Added

- **Per-agent channel webhooks**: new endpoints `GET/POST /v1/agents/{agent_name}/channels/{channel_type}/webhook` — each agent gets its own webhook URL with its own credentials, enabling multi-agent multi-channel deployments from a single runtime
- **Channel config resolver**: `astromesh/channels/resolver.py` — resolves `${ENV_VAR}` references in agent channel config, creates cached adapter instances per agent
- **Agent YAML channels spec**: agents can now declare `channels:` in their spec with per-channel config (tokens, secrets), replacing the global `channels.yaml` default_agent pattern

### Changed

- **Backward compatible**: existing global `/v1/channels/whatsapp/webhook` route stays as deprecated fallback

## [v0.24.0] - 2026-04-06

### Added

- **orbit**: Custom environment variables in Cloud Run — `OrbitSpec.env` dict rendered as additional env blocks in the Cloud Run template. Cortex injects workspace environment variables during provision
- **orbit**: Cloud Run services are now public by default (allUsers IAM binding) — enables Cortex browser to call runtime API without IAM tokens
- **orbit**: `OrbitMetadata.environment` now accepts `develop | staging | production` (was `dev`)

### Subpackage releases

- `astromesh-orbit` v0.2.0 — custom env vars, public Cloud Run, develop environment

## [v0.23.9] - 2026-04-06

### Fixed

- **api**: Default `ASTROMESH_CORS_ORIGINS` to `*` (was `http://localhost:5173`) — enables Cortex (Electron) to call the runtime API on Cloud Run deployments without CORS errors
- **orbit**: Removed reserved `PORT` env var from Cloud Run template — Cloud Run sets it automatically from the `ports` block

### Subpackage releases

- `astromesh-orbit` v0.1.10 — Cloud Run template PORT fix

## [v0.23.8] - 2026-04-06

### Fixed

- **orbit**: Set Cloud Run container port to 8000 (matching astromesh runtime's uvicorn default) with `ports` block and `PORT` env var in Cloud Run template

### Subpackage releases

- `astromesh-orbit` v0.1.9 — Cloud Run port 8000 fix

## [v0.23.7] - 2026-04-06

### Added

- **orbit**: Auto-create VPC peering for Cloud SQL during provision — `ensure_vpc_peering()` creates IP range + private services connection via google-auth API when `GOOGLE_APPLICATION_CREDENTIALS` is set
- **orbit**: `-lock=false` on all tofu commands (init, plan, apply, destroy) to prevent stale state lock conflicts in single-user Cortex deployments
- **orbit**: `-reconfigure` flag on `tofu init` to handle backend config changes without interactive prompts

### Fixed

- **orbit**: VPC access connector name truncated to 19 chars + "-vpc" suffix to meet GCP's 23-char limit

### Subpackage releases

- `astromesh-orbit` v0.1.8 — auto VPC peering, lock-free operations, init reconfigure

## [v0.23.6] - 2026-04-06

### Fixed

- **orbit**: `ensure_gcs_state_bucket` now uses `google-cloud-storage` Python library when `GOOGLE_APPLICATION_CREDENTIALS` is set, removing the hard dependency on `gsutil` CLI. Falls back to gsutil when no service account key is present. Handles `FileNotFoundError` gracefully when neither is available

### Changed

- **orbit**: Added `google-cloud-storage>=2.14` to `[gcp]` optional dependencies

### Subpackage releases

- `astromesh-orbit` v0.1.7 — GCS state bucket via Python API (no gsutil needed)

## [v0.23.5] - 2026-04-06

### Added

- **orbit**: `TerraformRunner` reads `TOFU_PATH` env var to locate the OpenTofu/Terraform binary, with fallback chain: `TOFU_PATH` -> `tofu` in PATH -> `terraform` in PATH. Enables Cortex to bundle OpenTofu without requiring system-wide install

### Subpackage releases

- `astromesh-orbit` v0.1.6 — `TOFU_PATH` env var support in TerraformRunner

## [v0.23.4] - 2026-04-06

### Fixed

- **orbit**: Replace Unicode symbols (✓, ✗, →, —) with ASCII equivalents in CLI output — fixes `UnicodeEncodeError` on Windows cp1252 consoles and Electron subprocess pipes

### Subpackage releases

- `astromesh-orbit` v0.1.5 — Windows-safe ASCII CLI output

## [v0.23.3] - 2026-04-06

### Added

- **orbit**: Dual-auth support in GCP validators — when `GOOGLE_APPLICATION_CREDENTIALS` is set, validators use `google-auth` + `google-cloud-resource-manager` libraries instead of requiring gcloud CLI. Auth, project, and API checks all auto-select the appropriate method

### Subpackage releases

- `astromesh-orbit` v0.1.4 — service account auth support in validators

## [v0.23.2] - 2026-04-06

### Fixed

- **orbit**: Handle missing gcloud CLI gracefully — `_run_gcloud` now catches `FileNotFoundError` and returns error code 127 instead of crashing with an unhandled exception when gcloud is not installed

### Subpackage releases

- `astromesh-orbit` v0.1.3 — graceful handling of missing gcloud CLI

## [v0.23.1] - 2026-04-06

### Fixed

- **orbit**: Use `gcloud.cmd` on Windows for `asyncio.create_subprocess_exec` — fixes `FileNotFoundError` when running `astromeshctl orbit plan/apply` on Windows

### Changed

- **docs**: Updated Ecosystem table with current versions — Core v0.23.1, CLI v0.1.1, Orbit v0.1.2; added Cortex v0.3.0 and Nexus v0.3.0 as new ecosystem components

### Subpackage releases

- `astromesh-orbit` v0.1.2 — Windows `gcloud.cmd` fix

## [v0.23.0] - 2026-03-30

**Subpackage releases:** core v0.23.0 | forge v0.23.0

### Added (Backend)

- **Trace query capture** — root `agent.run` spans now store the user query (up to 5k chars) as a `query` attribute
- **Trace input messages** — `llm.complete` spans now capture user-role messages as `input_messages` attribute for full trace visibility

### Added (Astromesh Forge)

- **Span input tab redesign** — input tab now shows User Query, Input Messages, and System Prompt as labeled sections with color-coded headers
- **Overview query preview** — span overview tab displays user query and input message previews with "View full input" links for long content
- **Input tab detection** — span detail panel now correctly enables the Input tab when `query` or `input_messages` attributes are present

## [v0.22.0] - 2026-03-30

**Subpackage releases:** core v0.22.0 | forge v0.22.0

### Added (Backend)

- **`psutil` dependency** — added `psutil>=5.9.0` to core dependencies for system resource monitoring
- **Example agent configs** — added `autolink-parts` (automotive parts advisor) and `chef-iberia` (Iberia chef assistant) agent YAML definitions
- **Config package** — added `astromesh/config/agents/` for bundled agent configurations

### Changed

- **Docs site dark-only theme** — removed light theme CSS fallback (`[data-theme='light']` block); consolidated `:root` declarations into a single dark-mode-only block

## [v0.21.0] - 2026-03-22

**Subpackage releases:** core v0.21.0 | forge v0.21.0

### Added (Backend)

- **Span enrichment** — `llm.complete` spans now capture model name, provider, latency (ms), estimated cost, rendered prompt (truncated at 10k chars), model response (truncated at 10k chars), and normalized tool calls
- **Tool span enrichment** — `tool.call` spans now capture tool arguments and execution result (truncated at 5k chars)
- **Orchestration step events** — `orchestration` span records each ReAct/PlanAndExecute step as a timestamped event with thought, action, action_input, observation, and result fields
- **Error capture** — all span error paths (`llm.complete`, `tool.call`, `agent.run`) now record `error_message` attribute
- **Helper functions** — `_truncate()` for safe text truncation, `_normalize_tool_calls()` for provider-agnostic tool call format, `_parse_args()` for JSON string argument handling (OpenAI compatibility)
- **Agent YAML persistence** — agents created or updated via the HTTP API (`POST /v1/agents`) are written to `agents/<name>.agent.yaml` under `ASTROMESH_CONFIG_DIR` when `ASTROMESH_PERSIST_AGENTS=1` (default). Set to `0` for tests.
- **Multi-root template discovery** — `GET /v1/templates` now merges `*.template.yaml` from multiple directories: bundled package templates, `${ASTROMESH_CONFIG_DIR}/templates`, `./config/templates`, and `ASTROMESH_TEMPLATES_DIR`. Later sources override earlier when names match. Empty directories no longer hide built-in templates.
- **Lifespan runtime wiring** — when runtime is pre-injected (e.g. by `astromeshd`), lifespan now wires all route modules (system, memory, whatsapp) instead of only agents

### Changed (Backend)

- **Node daemon template guard** — `astromeshd` skips `set_templates_dir` when `templates/` exists but contains no `*.template.yaml` files
- **Lifespan cleanup** — removed lifespan-level template directory management; templates route handles its own directory resolution

### Added (Astromesh Forge)

- **Span Detail Panel** — split-panel trace inspector with 7 tabbed views for deep debugging:
  - **Overview** tab: model/provider/latency/cost metrics grid, token usage (input/output/total), orchestration step visualization (thought → action → observation chain with colored borders), response preview, and error display
  - **Input** tab: full rendered prompt sent to the LLM
  - **Output** tab: full model response or tool execution result
  - **Tool Calls** tab: normalized tool call arguments and results as formatted JSON
  - **Guardrails** tab: guardrail events with action type coloring (ready for when guardrail execution is wired)
  - **Events** tab: chronological span events with relative timestamps
  - **Raw** tab: full JSON dump of span attributes and events with copy-to-clipboard
- **Chip indicators** — inline emoji badges on each span row indicating available data (💬 response, 🔧 tool calls, ✅ success, 📋 events, ⚠️ error, 🛡️ guardrails); clicking a chip opens the detail panel on the corresponding tab
- **Typed span attributes** — `SpanAttributes` interface replacing untyped `Record<string, unknown>` for type-safe attribute access
- **Popout detail panel** — maximize button opens span detail as a separate resizable panel between center and right panels; timeline stays visible for navigation; Esc to close; selecting a different span updates the popout automatically
- **Agent edit shortcuts** — Wizard and Canvas edit buttons in agent selector for quick navigation to `/wizard/{name}` and `/canvas/{name}`

### Changed (Astromesh Forge)

- **Resizable right panel** — panel width now adjustable via horizontal drag handle on left edge (280–900px range, persisted in localStorage); double-click handle to reset to default (420px)
- **Resizable popout panel** — popout detail panel width adjustable (320–1000px), also persisted in localStorage
- **Resizable vertical split** — timeline and detail panel heights adjustable via drag handle; detail panel only appears when a span is selected
- **Detail panel full height** — Input, Output, and Raw tabs now fill all available vertical space instead of being capped at 400px
- **Duration formatting** — span durations now display as human-readable values (`17.5s` instead of `17493.289947509766ms`)
- **Span selection** — clicking a span highlights it and loads its detail below; chevron click expands/collapses children independently of selection

### Fixed (Astromesh Forge)

- **Flat attribute reads** — `TraceTimeline` and `SpanNode` now read `input_tokens`/`output_tokens` directly from span attributes instead of broken nested `metadata.usage.prompt_tokens` path
- **Horizontal resize drag** — fixed closure capturing null element on mount; drag now uses `window.innerWidth - e.clientX` directly
- **Forge integration test** — template assertion now checks name membership instead of exact count, compatible with multi-root discovery
- **Test isolation** — `conftest.py` auto-disables agent YAML persistence (`ASTROMESH_PERSIST_AGENTS=0`) to prevent writing into repo during tests

## [v0.20.0] - 2026-03-21

**Subpackage releases:** core v0.20.0 | forge v0.20.0 | orbit v0.1.1 | adk v0.1.6 | cli v0.1.1 | node v0.1.1

### Added (Astromesh Forge)

- **Developer Console** (`/console`) — full-page playground for live agent testing and debugging
  - Three-column layout: agent config overrides (left), interactive chat (center), trace timeline (right)
  - Parameter overrides: change model, temperature, max_tokens, and toggle tools on/off without editing agent config
  - Trace timeline: hierarchical span tree (agent.run → memory_build → prompt_render → llm.complete → tool.call → memory_persist) with expandable details showing prompts, LLM responses, tool arguments/results, and token usage
  - Run history: clickable list of past runs in the current session
  - Compare mode: select two runs for side-by-side trace comparison with diff highlighting
  - Inline tool usage badges on assistant messages showing tool name and latency
  - Token/cost summary bar per run (tokens in/out, model, duration)
- **Canvas pipeline editing** — drag-and-drop pipeline blocks in micro-view
  - PipelinePropertiesPanel for editing block config within the canvas
  - `nodesToAgent` utility for canvas → AgentConfig roundtrip conversion
  - Pipeline graph utilities: append, remove, reconnect, and reposition nodes
  - Pipeline presets for common agent patterns
- **Lucide React icon library** — added `lucide-react` for consistent iconography across the UI
- **Toast notification system** — non-blocking toast notifications (success/error/info/warning) replacing browser `alert()` calls
- **Reusable UI primitives** — `Skeleton` (loading states), `EmptyState` (empty data views), `Tooltip` (hover hints)

### Changed (Astromesh Forge)

- **Header navigation** — icons on all nav links (Dashboard, Templates, Console), active route highlighting, Hexagon logo icon, Wifi/WifiOff/Loader2 connection status replacing colored dot
- **Dashboard** — QuickActions cards use proper icons (PlusCircle, LayoutTemplate, FileUp) replacing Unicode characters; AgentList shows Bot icons, status badge icons (FileEdit/CheckCircle2/PauseCircle), action button icons (Pencil/Rocket/Pause/Trash2), loading skeleton, and EmptyState for no agents/disconnected
- **Wizard step indicator** — step-specific icons (User, Cpu, Wrench, GitBranch, Settings, MessageSquare, ClipboardCheck) replacing step numbers; Check icon for completed steps
- **Console panels** — section header icons throughout (Bot, SlidersHorizontal, Terminal, Activity, History), Send icon button, Eraser/RotateCcw button icons, span type icons (Bot/Brain/Wrench/Shield/Database), ChevronDown/ChevronRight for expand/collapse
- **Compare mode redesign** — full-width layout replacing cramped 340px side panel; summary stat cards (duration/tokens/spans with delta percentages); span-by-span matched comparison with dual duration bars; inline run picker dropdowns to switch runs without exiting compare
- **Run summary bar** — now shows cumulative totals across all runs in the session instead of only the active run
- **Chat bubbles** — token usage (in/out) displayed on each assistant message
- **Canvas toolbox** — section icons (Wrench/Link2/Database/Shield/Cpu/Bot), ChevronUp/ChevronDown replacing Unicode arrows, Loader2 spinner for loading states
- **Templates gallery** — Search icon in search input, Skeleton card grid for loading, EmptyState for no results
- **Deploy modal** — ChevronRight icon replacing Unicode play triangle, Rocket icon on deploy button
- **Modal component** — X icon replacing Unicode `✕` close button
- **Button component** — optional `icon`/`iconRight` props for rendering Lucide icons
- **Badge component** — optional `icon` prop for rendering Lucide icons
- **Agent list Canvas button** — direct link to `/canvas/{name}` pipeline editor from the dashboard agent table

### Added (Backend)

- ASGI lifespan context manager (`astromesh/api/main.py`) — bootstraps AgentRuntime and wires all route modules automatically when running via `uvicorn`
- Template auto-discovery — `templates.py` resolves `config/templates/` via `ASTROMESH_TEMPLATES_DIR` env var, cwd, or package anchor without requiring explicit `set_templates_dir()` calls
- `AgentRunResponse.trace` field — run endpoint now returns full distributed trace data (previously computed but discarded)
- LLM provider auto-registration — `AgentRuntime._register_model_providers()` wires Ollama and OpenAI-compatible providers from agent YAML model spec
- Structured error types — `ModelProviderError` with typed payloads and 502 HTTP mapping in agent run endpoint
- Structured logging — `logging_config` module and debug logging in agent run endpoint (start/done with metrics)
- Model router improvements — better provider selection and error handling

### Fixed

- AgentRuntime skips agents that fail to build instead of crashing the entire bootstrap
- Forge wizard `StepIdentity` no longer crashes when identity fields are partially defined (e.g. from templates)
- `astromesh-copilot.agent.yaml` references updated to match available builtin tools (`json_transform`, `text_summarize` replacing removed `validate_yaml`, `list_builtin_tools`)
- Astromesh Node daemon gracefully handles missing dependencies
- Agent configs (sales-qualifier, support-agent, whatsapp-assistant) updated from Docker service name `ollama:11434` to `localhost:11434` for local development
- **Token usage extraction** — backend now correctly reads `input_tokens`/`output_tokens` from `span.attributes` (runtime format) in addition to legacy `span.attributes.metadata.usage` path
- **Compare mode button** — fixed `setCompare` always passing `null` in both branches of the ternary (never entering compare mode)

### Removed

- **`astromesh-cloud/`** — removed legacy cloud multi-tenant layer (API + Studio frontend). Auth, org management, BYOK, usage tracking, and execution proxy functionality will be absorbed by a future project
- **Cloud API and Studio from Orbit** — removed `cloud_api` and `studio` compute services, container images, and database from Orbit config, GCP provider, Terraform templates, wizard presets, and tests
- **Cloud documentation** — removed all 6 cloud docs pages
- **Nexus deploy target** — removed from Forge deployment docs

### Changed (Orbit)

- Deployment costs reduced: Starter ~$30 → **~$15/mo**, Pro ~$150 → **~$80/mo** (only runtime deployed)

### Changed (Tests)

- Test suite uses `asgi-lifespan` `LifespanManager` for proper runtime initialization
- Tests updated for draft lifecycle (`register_agent` → draft status in `_agent_configs`)
- Template tests use auto-discovery instead of hardcoded directory paths
- Forge client tests cover `runAgent`, `getTraces`, `getTrace` methods
- Added `nodes-to-agent` roundtrip tests for canvas pipeline editing

---

## [v0.19.3] - 2026-03-20

### Fixed

- Removed stale `test_init.py` from root tests (imported deleted `cli` module)
- Fixed `test_dynamic_agents.py` to match agent lifecycle: `register_agent` stores as draft in `_agent_configs`, not `_agents`
- Fixed `test_installer_windows.py` path comparisons for cross-platform CI

---

## [v0.19.2] - 2026-03-20

### Fixed

- Windows installer tests now use platform-agnostic path comparison (pass on Linux CI)
- CI workflow ignores doc-only changes (`paths-ignore` for docs/, docs-site/, *.md)
- PyPI publish no longer fails on re-publish (`skip-existing: true` for TestPyPI and PyPI)
- All release workflows use strict semver tag patterns (`v[0-9]+.[0-9]+.[0-9]+`)

---

## [v0.19.1] - 2026-03-20

### Changed (Docs-site)

- Replaced Cloud with Forge in ecosystem page (table, diagram, decision matrix, next steps)
- Updated SocialIcons version badges: removed Cloud, added CLI, Node, and Orbit
- Updated README ecosystem table: Cloud → Forge, Core version → v0.19.0
- Increased header logo size from 3.2rem to 4.2rem

---

## [v0.19.0] + [cli-v0.1.0] + [node-v0.1.0] - 2026-03-20

### Added (Astromesh CLI)

- **Astromesh CLI v0.1.0** (`astromesh-cli/`) — extracted from astromesh-node as standalone CLI tool for managing nodes and clusters
  - 14 daemon-client commands (status, doctor, agents, providers, mesh, peers, services, run, ask, traces, metrics, cost, tools, dev)
  - Scaffolding tool (`new`) for agents, workflows, and tools with Jinja2 templates
  - Plugin discovery system (`astromeshctl.plugins` entry points) — Node and Orbit register as plugins
  - HTTP client configurable via `ASTROMESH_DAEMON_URL` env var
  - 23 unit tests

### Added (Astromesh Forge)

- **Astromesh Forge** (`astromesh-forge/`) — visual agent builder SPA (Vite + React + TypeScript)
  - **Dashboard** — agent list with status indicators, quick actions, and search
  - **7-step Wizard** — identity, model, prompts, orchestration, tools, memory, guardrails
  - **Canvas** — macro (agent graph) and micro (pipeline) views with drag-and-drop nodes
  - **Templates gallery** — 15 pre-built agent templates with search, preview, and variable customization
  - **Deploy modal** — local, remote, and Nexus target selection
  - **Zustand stores** — connection, agent editor, and agent list state management
  - **Template engine** — YAML converter and canvas converters
  - **API client** — TypeScript types and HTTP client for Astromesh API
  - **Docs-site section** — 6 pages (introduction, quickstart, wizard guide, canvas guide, templates, deployment)

### Added (Core Runtime)

- **Agent status lifecycle** — draft → deployed → paused state machine with transitions
- **API endpoints** — PUT agent update, POST deploy, POST pause endpoints
- **Templates endpoint** — GET `/v1/templates/` serving 15 pre-built agent templates
- **CORS middleware** — configurable CORS for Forge SPA integration
- **Forge static mount** — serves Forge SPA from `/forge/` path

### Added (Templates)

- **15 pre-built agent templates** for business use cases in `config/templates/`

### Changed (Node)

- **BREAKING**: `astromeshctl` binary removed from astromesh-node — install via `astromesh-cli` package
- Node now registers `init`, `validate`, `config` as a plugin into `astromeshctl`
- Added `astromesh-cli>=0.1.0` as dependency for transition period

### Changed (Docs-site)

- **Ecosystem page** — new `getting-started/ecosystem.md` with component table, relationship diagram, decision matrix, and deployment layers
- **README** — ecosystem summary table with all 6 components, dedicated Node section, project structure updated

---

## [node-v0.1.0] - 2026-03-20

### Added (Astromesh Node)

- **Astromesh Node v0.1.0** (`astromesh-node/`) — cross-platform system installer and daemon, extracted from "Astromesh OS" as a standalone subproject
  - **ServiceManagerProtocol** — runtime-checkable Protocol abstracting init systems across platforms, following the same pattern as `ProviderProtocol`
  - **SystemdManager** (Linux) — `sd_notify` readiness signaling, `systemctl` service management, `SIGHUP` config reload
  - **LaunchdManager** (macOS) — `launchctl` plist management, `SIGHUP` config reload, `/Library/LaunchDaemons` integration
  - **WindowsServiceManager** — `win32serviceutil` / `sc.exe` fallback, Windows Service lifecycle management
  - **ForegroundManager** — no-op adapter for dev mode, Docker containers, and `--foreground` usage
  - **InstallerProtocol** — platform-specific filesystem paths and installation (Linux FHS, macOS `/Library/`, Windows `%ProgramData%`)
  - **Platform-agnostic daemon** (`astromeshd`) — refactored from monorepo `daemon/astromeshd.py` with `--foreground` flag, platform-aware config detection, and no hardcoded paths
  - **CLI migration** — `astromeshctl` (17 commands) moved to subproject with updated imports
  - **Packaging** — `.deb` (Debian/Ubuntu), `.rpm` (RHEL/Fedora), `.tar.gz` (macOS), `.zip` (Windows) build scripts; all artifacts published to GitHub Releases
  - **launchd plist** — `com.astromesh.daemon.plist` for macOS daemon registration
  - **Windows Service wrapper** — `astromeshd-service.py` using `win32serviceutil.ServiceFramework`
  - **`install.ps1`** — Windows installer script (directory creation, PATH setup)
  - **7 profiles** on all platforms — full, gateway, worker, inference, mesh-gateway, mesh-worker, mesh-inference
  - **Doctor migration check** — `astromeshctl doctor` warns about stale `astromesh` deb package on Linux
  - **55 unit tests** covering all platform adapters, installers, daemon config, and argument parsing

### Added (CI/CD)

- **`release-node.yml`** — GitHub Actions workflow triggered by `node-v*` tags; parallel build jobs for Linux (deb/rpm), macOS (tar.gz), Windows (zip); artifacts uploaded to GitHub Release
- **`test-node` CI job** — cross-platform test matrix (ubuntu, macos, windows) in `ci.yml`

### Added (Docs-site)

- **Astromesh Node documentation** — 9 new pages: introduction, quick start, 4 per-platform installation guides (Debian, RHEL, macOS, Windows), configuration, CLI reference, troubleshooting
- **NodeShowcase** — home page component showcasing 4 supported platforms with feature grid
- **Sidebar section** — "Astromesh Node" top-level section in docs navigation

### Changed

- **BREAKING**: Renamed "Astromesh OS" to "Astromesh Node" globally across codebase, docs, and CI
- **BREAKING**: `astromeshd` and `astromeshctl` entry points removed from root `pyproject.toml` — install via `astromesh-node` package
- `deployment/astromesh-os.md` replaced with redirect to `node/introduction`
- Root `pyproject.toml` no longer includes `cli` and `daemon` optional dependencies

### Removed

- `daemon/` directory from monorepo root (moved to `astromesh-node/src/astromesh_node/daemon/`)
- `cli/` directory from monorepo root (moved to `astromesh-node/src/astromesh_node/cli/`)
- `packaging/` directory and `nfpm.yaml` from monorepo root (moved to `astromesh-node/packaging/`)
- `build-deb` job from `release.yml` (replaced by `release-node.yml`)
- `build-deb-test` job from `ci.yml` (replaced by `test-node`)

---

## [v0.18.0] + [orbit-v0.1.0] - 2026-03-18

### Added (Orbit)

- **Astromesh Orbit v0.1.0** (`astromesh-orbit/`) — cloud-native deployment subproject for provisioning the full Astromesh stack on GCP using managed services
  - **Provider plugin architecture** — `OrbitProvider` Protocol (`@runtime_checkable`) with GCP as first implementation; generates Terraform HCL from Jinja2 templates
  - **GCP provider** — Cloud Run (runtime, cloud-api, studio) + Cloud SQL for PostgreSQL + Memorystore for Redis + Secret Manager + VPC Connector + IAM
  - **CLI plugin** — `astromeshctl orbit` with 6 commands: `init` (interactive wizard), `plan`, `apply`, `status`, `destroy`, `eject` (standalone Terraform export)
  - **Wizard presets** — Starter (~$30/mo) and Pro (~$150/mo) with explicit resource values
  - **orbit.yaml** — declarative config (`apiVersion: astromesh/v1, kind: OrbitDeployment`) with Pydantic v2 validation
  - **TerraformRunner** — async subprocess wrapper for terraform CLI
  - **State management** — remote GCS bucket with versioning and collision handling
  - **61 tests** covering config, core types, templates, provider, runner, and wizard

### Changed (CLI)

- **Plugin discovery** — `astromeshctl` now scans `importlib.metadata.entry_points(group="astromeshctl.plugins")` to discover and register external CLI plugins

### Added (Docs-site)

- **Orbit documentation** — 5 MDX pages (introduction, quickstart, configuration, GCP provider, CLI reference) with sidebar section
- **OrbitShowcase** — promotional component on docs-site homepage with feature cards and resource provisioning overview

### Added (Docs)

- **ORBIT_OVERVIEW.md** — architecture, provider plugins, multi-cloud vision, service roadmap
- **ORBIT_QUICKSTART.md** — install, GCP auth, init → plan → apply walkthrough, eject
- **ORBIT_CONFIGURATION.md** — complete orbit.yaml reference with all fields, presets, and validation rules

### Added (Cloud API)

- **Auto-migrate on startup** — `init_db()` creates all tables via `Base.metadata.create_all` during lifespan, removing the need for manual migration steps
- **Dockerfile** — production-ready container image for Cloud API (Python 3.12-slim, port 8001)

### Changed (Cloud API)

- **Dev login endpoint** — accepts JSON body (`DevLoginRequest`) in addition to query params; returns enriched `DevLoginResponse` with `token`, `user`, and `org_slug`; ensures existing users without an org get one created automatically
- **Default API port** — changed from 8000 to 8001 to avoid conflicts with Astromesh core runtime

### Changed (Cloud Studio)

- **API client endpoints** — aligned API key routes (`/api-keys` → `/keys`) and provider key routes to match Cloud API; added typed `ApiKeyRecord`; normalized response field mapping
- **Navigation routes** — simplified sidebar and agent card links by removing `orgSlug` prefix from paths
- **Deploy snippets** — base URL now reads from `NEXT_PUBLIC_API_URL` env var instead of deriving from `window.location`

### Fixed (Cloud Studio)

- **Usage page** — `formatNumber` now handles `null`/`undefined`/`NaN` values; usage data is normalized to handle alternate field names from the API (`total_tokens_in` → `tokens_in`, etc.)

### Added (Docs-site)

- **Astromesh Cloud documentation** — six new MDX pages under `docs-site/cloud/` (introduction, quickstart, studio guide, agent lifecycle, authentication, API reference) plus sidebar section; companion markdown docs in `docs/` (CLOUD_OVERVIEW, CLOUD_QUICKSTART, CLOUD_API_REFERENCE)

### Changed (Docs-site)

- **Hero logo size** — increased splash page logo from 420px to 560px max-width with stronger cyan glow
- **Header logo size** — bumped from 2.4rem to 3.2rem with stronger glow effect

### Fixed (Docs-site)

- **ADK version display** — ADKShowcase now reads version dynamically from `pyproject.toml` instead of a hardcoded string
- **Cloud MDX build** — escaped JSX variables in Cloud MDX files to fix Astro build errors

---

## [adk-v0.1.5] - 2026-03-17

### Fixed (ADK)

- **CLI dependencies** — moved `typer` and `rich` from optional `[cli]` extras to base dependencies; the `astromesh-adk` entry point always requires them
- **Build error** — removed stale `[cli]` reference from `[all]` optional-dependencies group that caused hatchling `ValueError`
- **TestPyPI smoke test** — added retry loop (5 attempts, 30s between) to handle TestPyPI indexing delay

### Changed (ADK)

- **Core dependency floor** — bumped to `astromesh>=0.17.2` to require runtime prerequisites (dynamic agent CRUD, BYOK, usage tracking)

## [v0.17.4] - 2026-03-17

### Fixed (Runtime)

- **Release workflow smoke tests** — added `--prefer-binary --only-binary=:all:` flags to pip install in TestPyPI smoke tests
- **TestPyPI smoke test** — added retry loop (5 attempts, 30s between) to handle TestPyPI indexing delay
- **Core smoke test** — replaced `astromeshctl --help` check with module import verification (`AgentRuntime`, `ModelRouter`); CLI entry point depends on `cli/` module not packaged in pip install
- **Test compatibility** — fixed CLI and daemon integration test imports

### Changed (Docs-site)

- **Header logo size** — increased from 1.6rem to 2.4rem for better visibility
- **Per-product version badges** — header now shows Core, ADK, and Cloud versions with color-coded badges (cyan/purple/green)
- **CI/CD status badges** — added StatusBadges component to homepage with CI, Release, Deploy Docs, Release PyPI, Release ADK workflows; Packages section with PyPI + TestPyPI versions; Info section with version, python, license
- **Badge reorganization** — moved Release PyPI and Release ADK badges from Packages to CI/CD group; added TestPyPI version badges

## [cloud-v0.1.0] - 2026-03-17

### Added (Cloud API)

- **Astromesh Cloud API** (`astromesh-cloud/api/`) — multi-tenant FastAPI service for managed AI agent platform
  - **Authentication** — Google/GitHub OAuth stubs + dev login; JWT access tokens (15 min) + refresh tokens (7 days); auto-creates organization on first login
  - **Organizations** — CRUD with slug-based routing; member management with invite; org limits (5 agents, 1000 req/day, 3 members)
  - **Agent lifecycle** — full state machine: `draft` → `deployed` → `paused`; wizard config stored as JSONB; runtime name namespaced as `{org_slug}--{agent_name}`
  - **Config builder** — translates wizard JSON (tone, model, tools, memory, guardrails, orchestration) into valid Astromesh agent YAML config
  - **Runtime proxy** — httpx client to Astromesh runtime with session ID prefixing (`{org_slug}:{session_id}`), BYOK header injection (`X-Astromesh-Provider-Key/Name`), and agent register/unregister
  - **API key management** — generate `am_` prefixed keys with bcrypt hashing; scoped access (`agent:run`, `agent:manage`); full key shown once on creation
  - **Provider key management** — Fernet-encrypted storage for BYOK keys (OpenAI, Anthropic, etc.); upsert semantics per provider
  - **Usage logging** — per-request token/cost tracking via `UsageLog`; aggregated summary endpoint filterable by period
  - **Rate limiting** — daily request count enforcement via DB query (Redis in v2)
  - **Reconciliation** — on startup, re-registers all `deployed` agents on the runtime if missing
  - **Docker Compose** — local dev setup with Cloud API + PostgreSQL
- **69 tests** covering all endpoints, services, and edge cases

### Added (Cloud Studio)

- **Astromesh Cloud Studio** (`astromesh-cloud/web/`) — Next.js 14 web app for no-code agent design and management
  - **Login page** — dev login flow with auto org creation; Google/GitHub OAuth placeholders
  - **Dashboard layout** — fixed sidebar navigation, auth guard, user header with logout
  - **Agent list** — responsive card grid with status badges (draft/deployed/paused with pulse dot); deploy/pause/delete actions; empty state with CTA
  - **Agent wizard** — 5-step guided flow:
    - Step 1 (Identity): name with auto-slug, system prompt, tone selector (Professional/Casual/Technical/Empathetic)
    - Step 2 (Model): curated cards — Free tier (Llama 3, Mistral, Phi-3) + BYOK (GPT-4o, Claude Sonnet, Gemini); routing strategy selector
    - Step 3 (Tools): 10 available tools with toggles + 12 "Coming Soon" tools with notify intent
    - Step 4 (Settings): memory toggle, PII/content guardrails, orchestration pattern selector with plain language
    - Step 5 (Deploy): YAML preview, inline test chat, deploy with API endpoint + code snippets (curl/Python/JS)
  - **Edit wizard** — loads existing agent config, "Update & Re-deploy" flow
  - **Settings pages** — org name/members management, API key creation with one-time display, provider key management (OpenAI/Anthropic/Google)
  - **Usage dashboard** — summary cards (requests, tokens, cost) with 7d/30d/90d period selector
  - **Astromesh brand palette** — cyan `#00d4ff` accent, dark surfaces, DM Sans + JetBrains Mono fonts
  - **Dockerfile** — multi-stage build with standalone Next.js output

## [v0.17.0] - 2026-03-17

### Added (Runtime)

- **Dynamic agent CRUD** — `register_agent(config)` and `unregister_agent(name)` methods on `AgentRuntime`; upsert semantics for idempotent reconciliation
- **`POST /v1/agents`** — register a new agent dynamically from JSON config (same schema as YAML)
- **`DELETE /v1/agents/{name}`** — remove a dynamically registered agent
- **BYOK provider key override** — `X-Astromesh-Provider-Key` and `X-Astromesh-Provider-Name` headers on `POST /v1/agents/{name}/run`; request-scoped provider override passed to `ModelRouter`; key never persisted
- **Provider factory** (`astromesh/providers/factory.py`) — `create_provider(name, api_key)` for dynamic provider instantiation (used by BYOK flow)
- **Usage in response** — `AgentRunResponse` now includes optional `usage` field (`tokens_in`, `tokens_out`, `model`) extracted from trace spans
- **Memory delete endpoint** — `DELETE /v1/memory/{agent}/history/{session}` now functional (was stub); wired via `set_runtime` pattern

### Added (Docs-site)

- **Header logo** — replaced text title with Astromesh logo image via Starlight `logo.replacesTitle`
- **FeatureCards redesign** — bento-grid layout with 2 hero cards + 4 compact cards; accent top borders, radial gradient hover glow, tag badges
- **DevToolkit redesign** — segmented tab control with equal-width columns; capability cards with accent left borders, numbered indices, terminal-style `$` prompt, slide-in animations
- **ADK Showcase version** — updated badge to v0.16.1

## [0.16.1] - 2026-03-17

### Added

- **ADK Showcase component** (`docs-site/src/components/ADKShowcase.astro`) — animated hero section on the docs homepage featuring live code preview with line-by-line reveal, 6-card feature grid, terminal install preview, and gradient CTA buttons; ambient orb backgrounds with grid overlay
- **ADK docs-site pages** — 5 content pages completing the ADK sidebar: Defining Agents, Creating Tools, Multi-Agent Teams, Remote Execution, CLI Reference

### Fixed

- **ADK code panel rendering** — replaced `<pre>/<code>` with div-based flex layout to eliminate empty line artifacts (`}` characters) and excessive vertical spacing; compact line height with proper whitespace handling
- **Homepage section order** — moved Agent Execution Pipeline before ADK Showcase; the pipeline is the core of Astromesh and should be the first section after the hero

## [0.16.0] - 2026-03-17

### Added

- **Astromesh ADK** (`astromesh-adk/`) — Python-first Agent Development Kit for building, running, and deploying AI agents with decorator and class APIs
  - **`@agent` decorator** — define agents from async functions; docstring becomes system prompt, body is the run handler with `RunContext` access to `run_default()`, `complete()`, `call_tool()`
  - **`Agent` base class** — class-based agents with lifecycle hooks (`on_before_run`, `on_after_run`, `on_tool_call`) and dynamic system prompts via `system_prompt_fn(ctx)`
  - **`@tool` decorator** — define tools from async functions with auto-generated JSON schema from Python type hints (str, int, float, bool, list, dict, Optional, `X | None`)
  - **`Tool` ABC** — stateful tools with explicit `parameters()` schema, `execute()`, and `cleanup()` lifecycle
  - **`MCPToolSet`** — lazy MCP server integration via `mcp_tools()`; synchronous creation at import time, async discovery on first agent run; supports `*` unpacking in tools list
  - **`AgentTeam`** — multi-agent composition with 4 orchestration patterns: `supervisor` (delegate to workers), `swarm` (agents hand off), `pipeline` (sequential chain), `parallel` (fan-out + aggregate)
  - **Provider resolution** — `"provider/model"` string shorthand (e.g., `"openai/gpt-4o"`, `"ollama/llama3"`) auto-resolves to Astromesh provider instances with API keys from env vars
  - **Memory config builder** — string shorthand (`memory="sqlite"`) or full dict config normalized to Astromesh `MemoryManager` format
  - **Guardrails config builder** — string shorthand (`["pii_detection"]`) expanded with default actions per guardrail type
  - **Remote connection** — `connect()`, `disconnect()`, `remote()` context manager with `contextvars.ContextVar` for async-safe concurrent execution; per-agent `bind()` for targeted remote dispatch
  - **`RunResult`** — structured result with `answer`, `steps`, `trace`, `cost`, `tokens`, `latency_ms`, `model`; built from `TracingContext` span aggregation
  - **`StreamEvent`** — typed events (`"step"`, `"token"`, `"done"`) for streaming agent execution
  - **`RunContext`** — rich context object with `query`, `session_id`, `agent_name`, `user_id`, `memory` accessor, `tools` list, and methods for `run_default()`, `complete()`, `call_tool()`
  - **`Callbacks`** — observational base class (`on_step`, `on_tool_result`, `on_model_call`, `on_error`) distinct from agent lifecycle hooks; errors in callbacks are logged, never propagated
  - **Exception hierarchy** — `ADKError` base with typed subtrees: `AgentError`, `ProviderError`, `ToolError`, `GuardrailError`, `RemoteError` (each with specific subtypes)
  - **`ADKRuntime`** — embedded runtime with `start()`/`shutdown()` lifecycle and context manager support; implicit runtime via `atexit` for scripts
  - **CLI** (`astromesh-adk`) — 5 commands: `run` (one-shot execution), `chat` (interactive terminal), `list` (show agents in file), `check` (validate config, env vars, tools), `dev` (FastAPI dev server with hot reload)
  - **Public API** — 16 exports from `astromesh_adk`: `Agent`, `agent`, `AgentTeam`, `ADKRuntime`, `Callbacks`, `RunContext`, `RunResult`, `StreamEvent`, `Tool`, `tool`, `ToolContext`, `connect`, `disconnect`, `remote`, `mcp_tools`, `AgentWrapper`
- **ADK examples** — `quickstart.py`, `tools_example.py` (decorator + class tools), `multi_agent.py` (pipeline + supervisor teams)
- **ADK documentation** — `docs/ADK_QUICKSTART.md` getting started guide, `docs/ADK_PENDING.md` implementation roadmap
- **Docs-site ADK section** — 7 sidebar entries in Astro Starlight with `introduction.mdx` and `quickstart.mdx` pages
- **ADK design spec** (`docs/superpowers/specs/2026-03-17-astromesh-adk-design.md`) — 16-section approved design covering all ADK subsystems
- **ADK implementation plan** (`docs/superpowers/plans/2026-03-17-astromesh-adk.md`) — 18-task plan with TDD steps, reviewed and approved
- 89 new tests for all ADK modules

### Changed

- **Docs-site sidebar** (`docs-site/astro.config.mjs`) — added "Agent Development Kit" section with 7 pages

## [0.15.4] - 2026-03-12

### Fixed

- **Dockerfile** — create minimal package skeleton (`astromesh/`, `daemon/`, `cli/` with `__init__.py`) before dependency install so hatchling can resolve extras without the full source tree, keeping the dependency layer cacheable

## [0.15.3] - 2026-03-12

### Added

- **`.dockerignore`** — excludes dev/build artifacts (`.git`, `.venv`, `node_modules`, `tests`, `docs`, etc.) from Docker build context for faster, leaner builds

### Changed

- **Dockerfile** — optimized multi-stage build with cache-friendly layer separation: dependencies install before source copy so code changes don't invalidate the dependency cache; extras are now configurable via `ASTROMESH_EXTRAS` build arg (defaults to all runtime extras minus `all`)

## [0.15.2] - 2026-03-12

### Changed

- **Release workflow** — disabled APT repo publish step while public endpoint is pending

### Fixed

- **DevToolkit tab icons** — normalized SVG sizing via CSS (`14px` fixed dimensions) so CLI, Copilot, and VS Code icons render at consistent visual weight

## [0.15.1] - 2026-03-10

### Fixed

- **Dockerfile** — add missing `COPY README.md .` so the build no longer fails when hatchling reads the readme declared in `pyproject.toml`

## [0.15.0] - 2026-03-10

### Added

- **Version badge in docs-site header** (`docs-site/src/components/SocialIcons.astro`) — displays active version (from `pyproject.toml`) as a clickable pill badge next to the GitHub icon, linking to the release page
- **Developer Toolkit component** (`docs-site/src/components/DevToolkit.astro`) — interactive tabbed showcase on the docs homepage highlighting CLI, Copilot, and VS Code Extension with capability cards, accent colors, and "Coming Soon" cluster orchestration callout

### Changed

- **Developer Tools guide** (`docs-site/getting-started/developer-tools`) — restructured into three clear sections (CLI, Copilot, VS Code) with command examples, feature table, and quick reference
- **Docs-site content** — formatting and alignment fixes across architecture, reference, and deployment pages
- **License references in docs** — updated `README.md` and `docs/TECH_OVERVIEW.md` to Apache-2.0 and aligned with canonical `LICENSE`
- **Installation docs** — switched from APT repo URL to GitHub `.deb` releases for clearer install instructions

### Fixed

- **Release packaging** — hardened version checks and packaging scripts for reliable releases

## [0.14.0] - 2026-03-10

### Added

- **VS Code Extension** (`vscode-extension/`) — official extension wrapping `astromeshctl` CLI with zero business logic in the extension
  - **YAML IntelliSense** — JSON Schemas for `*.agent.yaml` and `*.workflow.yaml` with auto-completion, validation, and hover docs (requires Red Hat YAML extension)
  - **Run Agent** — play button on `.agent.yaml` files, extracts agent name from YAML, prompts for query, shows response in Output panel
  - **Run Workflow** — play button on `.workflow.yaml` files with `--workflow` flag passthrough
  - **Workflow Visualizer** — webview DAG panel with color-coded step types (agent=green, tool=yellow, switch=purple), connectors, and goto labels
  - **Traces Panel** — TreeDataProvider sidebar with expandable span trees, auto-refresh (configurable interval), and manual refresh command
  - **Metrics Dashboard** — webview panel with counters grid and histograms table, auto-refresh every 10s, VS Code theme integration
  - **Copilot Chat** — interactive chat panel wrapping `astromesh ask` with user/assistant message bubbles and loading states
  - **Diagnostics** — command wrapping `astromesh doctor` with check-by-check output and health status notification
  - **Status Bar** — daemon status indicator showing agent count, version, mode; click to run diagnostics
  - **CLI Wrapper** (`src/cli.ts`) — `AstromeshCli` class with `exec`, `execJson`, `buildArgs`, `parseJsonOutput` for spawning CLI commands
  - Extension settings: `astromesh.cliPath`, `astromesh.daemonUrl`, `astromesh.traces.autoRefresh`, `astromesh.traces.refreshInterval`
  - 6 extension unit tests (CLI wrapper + traces logic)
- **Developer Tools Guide** (`docs-site/src/content/docs/getting-started/developer-tools.md`) — step-by-step workflow from scaffold to production: Define → Run → Debug → Optimize → Deploy
- **VS Code Extension Reference** (`docs-site/src/content/docs/reference/os/vscode-extension.md`) — full feature reference with installation, settings, and usage
- **Developer Tools doc** (`docs/DEVELOPER_TOOLS.md`) — CLI command table, Copilot, VS Code Extension features, Dashboard overview
- **README Developer Experience section** — toolkit table (CLI, Copilot, VS Code, Dashboard) with 5-command workflow example
- **README Roadmap update** — 10 completed items including VS Code extension, 5 remaining items
- docs-site sidebar entries for Developer Tools and VS Code Extension (42 pages total)

### Changed

- **README Tool System section** — updated to reflect 18 built-in tools, 3 MCP servers, agent tools, webhooks, RAG
- **README Observability section** — expanded with CLI commands, dashboard URL, OTel export, VS Code integration

## [0.13.0] - 2026-03-10

### Added

- **Workflow Engine** — `WorkflowSpec`, `StepSpec`, `StepResult`, `RetryConfig` dataclasses for YAML-defined multi-step workflows (`astromesh/v1 Workflow`)
- **Workflow Loader** — reads `*.workflow.yaml` from `config/workflows/`, validates schema, registers workflows at bootstrap
- **Step Executor** — handles 3 step types: agent (via `runtime.run()`), tool (via `tool_registry.execute()`), switch (Jinja2 conditional with `goto`)
- **Retry & Timeout** — per-step retry with fixed/exponential backoff via `asyncio.sleep`, per-step and workflow-level timeouts via `asyncio.wait_for`
- **Error Handling** — `on_error` field per step (goto another step or `"fail"` to abort); workflow-level `timeout_seconds`
- **Workflow API** — `POST /v1/workflows/{name}/run`, `GET /v1/workflows`, `GET /v1/workflows/{name}` with `set_workflow_engine()` injection pattern
- **Built-in Dashboard** — single-page HTML at `GET /v1/dashboard/` with auto-refreshing (10s) panels for counters, histograms, traces, and workflows; dark theme matching Astromesh branding
- **CLI Workflow Execution** — `astromeshctl run --workflow` now calls `POST /v1/workflows/{name}/run` (replaces Sub-project 4 stub)
- **Example Workflow** — `config/workflows/example.workflow.yaml` (lead qualification pipeline with research → qualify → decide → send-email/log-and-skip)
- 59 new tests for workflow models, loader, executor, engine, API, dashboard, and CLI wiring

### Changed

- **`astromesh/api/main.py`** — mounts `workflows.router` and `dashboard.router` at `/v1`
- **`cli/commands/run.py`** — replaces "not yet implemented" stub with actual workflow API call
- **`cli/templates/workflow.yaml.j2`** — updated with full workflow schema including triggers, steps, retry, and observability config

## [0.12.0] - 2026-03-10

### Added

- **Built-in Tool Framework** — `BuiltinTool` ABC, `ToolResult`/`ToolContext` dataclasses, and `ToolLoader` with auto-discovery for registering tools via `type: builtin` in agent YAML
- **17 Built-in Tools** across 7 categories:
  - **Utilities** — `datetime_now` (timezone-aware), `json_transform` (Jinja2 templates), `cache_store` (key-value sharing between tool calls)
  - **HTTP** — `http_request` (GET/POST/PUT/DELETE/PATCH with localhost blocking), `graphql_query`
  - **Web** — `web_search` (Tavily provider), `web_scrape` (HTML-to-text), `wikipedia` (article summaries)
  - **Files** — `read_file`, `write_file` (both with configurable `allowed_paths` restrictions)
  - **Database** — `sql_query` (SQLite, `read_only: true` by default, blocks INSERT/UPDATE/DELETE/DROP)
  - **Communication** — `send_webhook`, `send_slack` (via webhook), `send_email` (async SMTP via `asyncio.to_thread`)
  - **AI** — `text_summarize` (delegates to agent's model via `model_fn`, skips short text)
  - **RAG** — `rag_query`, `rag_ingest` (wraps existing RAG pipeline)
- **`GET /v1/tools/builtin`** — API endpoint listing all available builtin tools with metadata (name, description, parameters)
- **TracingContext** — lightweight span-based tracing with `start_span()`/`finish_span()`, nested spans, and `to_dict()` serialization
- **Runtime tracing** — `Agent.run()` automatically creates spans for `memory_build`, `prompt_render`, `llm.complete`, `tool.call`, `orchestration`, `memory_persist`; trace attached to result as `result["trace"]`
- **StructuredLogger** — JSON-to-stdout logger with `info()`/`warning()`/`error()`/`debug()` methods
- **Trace collectors** — `StdoutCollector` (JSON to stream), `InternalCollector` (in-memory deque with index), `OTLPCollector` (bridges to existing `TelemetryManager` for OpenTelemetry export)
- **`GET /v1/traces/`** — list traces with optional `?agent=` filter and `?limit=` pagination
- **`GET /v1/traces/{trace_id}`** — retrieve individual trace by ID (404 on miss)
- **`GET /v1/metrics/`** — in-memory counters and histograms (count, sum, avg, min, max)
- **`POST /v1/metrics/reset`** — clear all metrics
- **Ecosystem design spec** (`docs/superpowers/specs/2026-03-10-astromesh-ecosystem-design.md`) — 5 sub-project architecture for tools, observability, multi-agent, CLI/copilot, and VS Code extension
- 93 new tests for all tools, tracing, collectors, APIs, and registry
- **CLI Scaffolding Commands** — `astromeshctl new agent|workflow|tool` generates YAML/Python from Jinja2 templates with interactive prompts and `--force` overwrite support
- **CLI Execution Commands** — `astromeshctl run <agent> "query"` executes agents via REST API; `astromeshctl dev` starts hot-reload dev server with `uvicorn --reload`
- **CLI Observability Commands** — `astromeshctl traces <agent>` lists recent traces; `astromeshctl trace <id>` shows span tree; `astromeshctl metrics` and `astromeshctl cost` show aggregated metrics
- **CLI Tools Commands** — `astromeshctl tools list` shows available builtin tools; `astromeshctl tools test <name> '{args}'` tests tools in isolation
- **CLI Validation** — `astromeshctl validate` checks all `*.agent.yaml` and `*.workflow.yaml` files for schema compliance
- **Copilot Agent** — `astromeshctl ask "question"` runs an astromesh-copilot agent locally with sandboxed filesystem access and `--context` file support; agent YAML at `config/agents/astromesh-copilot.agent.yaml`
- **Agent-as-Tool** — new `type: agent` tool type allows agents to invoke other agents as tools; registered via `register_agent_tool()` with full ToolResult integration
- **Context Transforms** — Jinja2-based data reshaping between agent-to-agent calls via `context_transform` field in tool YAML; uses `_DotDict` for dot-notation access
- **Nested Agent Tracing** — agent-in-agent calls share trace tree via `parent_trace_id` propagation; child agents create spans under parent's trace
- **Circular Reference Detection** — DFS cycle detection at bootstrap prevents infinite agent-as-tool reference loops
- **Multi-agent Composition docs** — new docs-site page covering agent-as-tool, context transforms, and supervisor/swarm integration
- 68 new tests for CLI commands, agent-as-tool, context transforms, supervisor/swarm agent integration
- 33 CLI tests + 35 multi-agent tests

### Changed

- **License** — consolidated into single `LICENSE` file (Apache 2.0), removed `LICENSE.md`
- **NOTICE.md** — updated repo URL, added managed runtime and enterprise support to commercial offerings
- **Repo rename** — all references to `astromech-platform` replaced with `astromesh` across docs, configs, CI, Helm chart, Dockerfile, packaging, and docs-site (29 files, 78 occurrences)
- **README CI badge** — CI badge now tracks `main` branch instead of `develop`
- **Docs site visual redesign** — replaced emoji icons with SVG Lucide icons across all landing page components for consistent cross-platform rendering
- **PipelineDiagram** — redesigned with gradient icon circles, numbered steps, dashed SVG connectors, glow effects, and staggered animations; each step is now a clickable link to its relevant docs page; responsive flex layout (no horizontal scroll)
- **FeatureCards** — per-card accent colors with tinted SVG icon backgrounds, refined expand/collapse chevron
- **DeploymentTabs** — dark chrome tab bar with per-mode SVG icons, unified glass-morphism surface
- **AgentExample** — macOS-style window chrome (traffic light dots), uppercase response label
- **Custom CSS** — replaced Inter font with DM Sans + JetBrains Mono; added custom design tokens (`--am-glow`, `--am-surface`, `--am-border`) for cohesive aerospace aesthetic
- **Color palette rebrand** — accent palette shifted from blue (`#3b82f6`) to logo-derived cyan (`#00d4ff`); updated all CSS variables, component fallback values, and gradient endpoints (`#06b6d4`) across `custom.css`, `PipelineDiagram`, `FeatureCards`, `DeploymentTabs`, and `AgentExample`
- **`astromesh/runtime/engine.py`** — `_build_agent()` now resolves `type: builtin` tools via `ToolLoader`; `Agent.run()` wrapped with `TracingContext` for automatic span collection
- **`astromesh/api/main.py`** — mounts `traces` and `metrics` routers at `/v1`
- **`astromesh/observability/collector.py`** — refactored with `Collector` ABC; added `OTLPCollector` bridging to OpenTelemetry
- **`astromesh/core/tools.py`** — added `ToolType.AGENT` enum, `agent_config`/`context_transform` fields to `ToolDefinition`, `register_agent_tool()` and `set_runtime()` methods, Jinja2 context transform execution in AGENT branch
- **`astromesh/orchestration/supervisor.py`** — delegates to workers via `tool_fn` instead of direct `model_fn` calls, enabling agent-as-tool delegation
- **`astromesh/orchestration/swarm.py`** — handoffs now use `tool_fn` to invoke agent tools, supporting `type: agent` handoff targets
- **`astromesh/runtime/engine.py`** — wires `type: agent` tools in `_build_agent()`, passes runtime reference to ToolRegistry, adds `_detect_circular_refs()` DFS at bootstrap, `parent_trace_id` propagation
- **`astromesh/observability/tracing.py`** — `start_span()` now accepts optional `parent_span_id` parameter for explicit parent override
- **`cli/main.py`** — registered 8 new command groups (new, run, dev, traces, metrics, tools, validate, ask)
- **`cli/client.py`** — added `api_post_with_timeout()` and `api_get_params()` helper methods
- **`cli/output.py`** — added Rich formatters: `print_trace_list()`, `print_trace_tree()`, `print_metrics_table()`, `print_cost_table()`, `print_tool_list()`

### Added (docs-site)

- **Dark mode lock** — theme toggle removed via Starlight `ThemeSelect` component override; dark mode is now permanent with CSS fallback for any light-theme tokens
- **Astromesh logo** in docs-site landing page hero with blue glow drop-shadow and entrance animation
- "Read full pipeline documentation" CTA button below pipeline diagram linking to `/architecture/agent-pipeline/`
- **README badges** — CI, Release, Docs (workflow status), Version, License, Python version
- **README navigation links** — Documentation site, Quick Start, Releases centered below badges
- Docs site link as primary documentation entry point in README
- Additional doc references in README: Maia guide, Dev quickstart, Installation

### Changed (docs-site)

- **README** — clone URL updated from `your-org` to `monaccode`

### Fixed

- "Get Started" hero button now correctly links to `/astromesh/getting-started/what-is-astromesh/` (was missing `/astromesh` base path)
- Docs CI workflow updated to Node 22 for Astro 5.x compatibility
- Removed broken GitHub raw logo image from landing page
- WhatsApp integration docs formatting fix
- Deployment options table in "What is Astromesh?" now uses "View guide →" link text instead of repeating the deployment name

## [0.11.0] - 2026-03-09

### Added

- **Docker Hub pre-built image** — `monaccode/astromesh:latest` with smart entrypoint that generates config from environment variables (`docker/entrypoint.sh`)
- Entrypoint supports `ASTROMESH_ROLE`, `ASTROMESH_MESH_ENABLED`, `ASTROMESH_NODE_NAME`, `ASTROMESH_SEEDS`, `ASTROMESH_PORT` env vars for zero-config deployment
- `ASTROMESH_AUTO_CONFIG=false` opt-out for users mounting their own `runtime.yaml`
- **4 Docker Compose recipes** (`recipes/`) — pre-built image, no source checkout needed:
  - `single-node.yml` — single full node with Ollama
  - `mesh-3node.yml` — gateway + worker + inference with Maia gossip discovery
  - `mesh-gpu.yml` — mesh with NVIDIA GPU acceleration for Ollama
  - `dev-full.yml` — full stack with Prometheus, Grafana, and OpenTelemetry Collector
- **Docker Hub CI** — `build-docker` job in `.github/workflows/release.yml` pushes `monaccode/astromesh:<version>` and `monaccode/astromesh:latest` on release tags
- **Maia Developer Guide** (`docs/MAIA_GUIDE.md`) — hands-on guide with recipes reference, environment variables, config generation, profiles, scaling, troubleshooting
- **Documentation site** (`docs-site/`) — Starlight (Astro) static site with 37 pages:
  - Interactive landing page with animated pipeline diagram, expandable feature cards, deployment tabs with copy-to-clipboard, and agent YAML split-pane example
  - Getting Started (4 pages): What is Astromesh, Installation, Quick Start, Your First Agent
  - Architecture (4 pages): Overview, Four-Layer Design, Agent Execution Pipeline, K8s Architecture
  - Configuration (6 pages): Init Wizard, Agent YAML Schema, Providers, Runtime Config, Profiles, Channels
  - Deployment (7 pages): Standalone, Astromesh OS, Docker Single, Docker Maia, Docker Maia+GPU, Helm/K8s, ArgoCD/GitOps
  - Advanced (4 pages): Rust Extensions, WhatsApp Integration, Observability, Maia Internals
  - Reference (11 pages): Runtime Engine, Model Router, Tool Registry, Memory Manager, Daemon, CLI, Gossip Protocol, Scheduling, Env Vars, API Endpoints, CLI Commands
- **Docs CI** — `.github/workflows/docs.yml` auto-deploys to GitHub Pages on push to `develop`
- 4 interactive Astro components: `PipelineDiagram`, `FeatureCards`, `DeploymentTabs`, `AgentExample`

### Changed

- `Dockerfile` — added entrypoint script, ENV defaults, changed ENTRYPOINT from `astromeshd` to `/usr/local/bin/entrypoint.sh`
- `docs/ASTROMESH_MAIA.md` — added pointer to MAIA_GUIDE.md developer guide
- `docs/DEV_QUICKSTART.md` — added reference to `recipes/` for pre-built image users
- `.gitignore` — added `docs-site/node_modules/`, `docs-site/dist/`, `docs-site/.astro/`

## [0.10.0] - 2026-03-09

### Added

- **`astromeshctl init` wizard** — interactive setup command that guides developers from zero to a running node: role selection, provider configuration, mesh setup, config file generation, and validation (`cli/commands/init.py`)
- Wizard supports `--non-interactive` mode for CI/scripting (defaults: role=full, provider=ollama)
- Wizard supports `--dev` flag to force local `./config/` mode even as root
- Provider auto-detection: checks Ollama connectivity, prompts API keys for OpenAI/Anthropic, writes `.env` file
- Mesh configuration step for non-full roles: node name, seed URLs, gossip parameters
- Config validation step reusing `astromeshctl config validate` logic
- Sample agents automatically copied to `{config_dir}/agents/` during init
- **One-liner install script** (`packaging/get-astromesh.sh`) — `curl | bash` installer with OS detection, APT repo setup, Python version check, and Docker fallback for non-Debian systems
- **Makefile** with developer targets: `dev-single`, `dev-mesh`, `dev-stop`, `dev-logs`, `test`, `test-cov`, `lint`, `fmt`, `build-deb`, `build-rust`
- **Developer Quick-Start guide** (`docs/DEV_QUICKSTART.md`) — prerequisites, single-node setup, Docker mesh, first agent, Makefile reference, troubleshooting
- Tests for init wizard: profile copy, provider generation (ollama/openai/anthropic), `.env` writing, idempotency, non-interactive mode, validation, dev mode, agents directory (10 new tests, 342 total)

### Changed

- `packaging/systemd/astromeshd.service` — added `EnvironmentFile=-/etc/astromesh/.env` for API key injection
- `packaging/scripts/postinstall.sh` — added hint to run `astromeshctl init` after package install
- `cli/main.py` — registered `init` command

### Fixed

- Version assertions in `test_cli.py` and `test_daemon_integration.py` updated from hardcoded `0.7.0` to match current version

## [0.9.0] - 2026-03-09

### Added

- **APT package distribution** — users can install Astromesh via `apt install astromesh` from a GitHub Pages-hosted APT repository
- `nfpm.yaml` — package definition for nfpm: self-contained Python venv at `/opt/astromesh/venv/`, symlinks to `/usr/bin/`, config files as conffiles (preserved on upgrade)
- Maintainer scripts (`packaging/scripts/`):
  - `preinstall.sh` — idempotent `astromesh` system user/group creation
  - `postinstall.sh` — runtime dirs, permissions, systemd enable (no auto-start)
  - `preremove.sh` — stop and disable service
  - `postremove.sh` — cleanup on purge (data, logs, user), daemon-reload always
- `packaging/build-deb.sh` — build orchestration: extracts version from pyproject.toml, creates venv with `[cli,daemon]` extras, strips `__pycache__`, runs nfpm
- `.github/workflows/release.yml` — CI/CD pipeline triggered on `v*` tags:
  - `build-deb` job: builds `.deb` package
  - `publish-apt-repo` job: updates GitHub Pages APT repository with signed metadata (GPG)
  - `release-assets` job: uploads `.deb` to GitHub Releases
- `build-deb-test` job in CI workflow — verifies `.deb` builds correctly on every PR
- `docs/INSTALLATION.md` — user-facing guide: APT repo setup, configuration, service management, upgrading, uninstalling

### Changed

- `packaging/systemd/astromeshd.service` — `ExecStart` updated from `/opt/astromesh/bin/astromeshd` to `/opt/astromesh/venv/bin/astromeshd`

## [0.8.0] - 2026-03-09

### Added

- **Astromesh Mesh** — gossip-based distributed multi-node agent execution
- **MeshManager** (`astromesh/mesh/manager.py`) — HTTP gossip protocol with periodic heartbeats, failure detection (alive → suspect → dead), and seed-based cluster join/leave
- **LeaderElector** (`astromesh/mesh/leader.py`) — bully algorithm leader election (highest node ID wins), automatic re-election on leader failure
- **Scheduler** (`astromesh/mesh/scheduler.py`) — two-level scheduling: least-loaded agent placement across worker nodes, least-connections request routing
- **NodeState/ClusterState** (`astromesh/mesh/state.py`) — mesh data models with serialization, gossip merge (keep latest heartbeat), and alive node filtering
- **MeshConfig** (`astromesh/mesh/config.py`) — configuration for mesh networking: seeds, heartbeat/gossip intervals, failure/dead timeouts, gossip fanout
- **Mesh API endpoints** (`astromesh/api/routes/mesh.py`) — `POST /v1/mesh/join`, `/leave`, `/heartbeat`, `/gossip`, `/election`, `GET /v1/mesh/state`
- **PeerClient.from_mesh()** — bridges mesh discovery into existing peer forwarding infrastructure; dynamic peers from cluster state replace static config
- `astromeshctl mesh status` — mesh cluster summary (nodes, leader, alive/suspect/dead counts)
- `astromeshctl mesh nodes` — Rich table with all nodes: name, URL, services, agents, load, status, leader flag
- `astromeshctl mesh leave` — graceful mesh departure
- Mesh-enabled config profiles: `mesh-gateway.yaml`, `mesh-worker.yaml`, `mesh-inference.yaml` (`config/profiles/`)
- Docker Compose gossip mesh for local development (`docker/docker-compose.gossip.yml`)
- Background gossip and heartbeat loops in daemon with graceful cleanup on shutdown
- `GET /v1/system/status` now includes `mesh` section (node_id, leader, cluster_size, status)
- `psutil` optional dependency for CPU/memory load metrics (`[mesh]` extra)
- Mesh design and implementation plan documents (`docs/plans/2026-03-09-astromesh-mesh-*.md`)
- Tests for all mesh components: state, config, manager, leader, scheduler, API, PeerClient bridge, daemon wiring, and 3-node integration (78 new tests, 332 total)

### Changed

- `daemon/astromeshd.py` parses `spec.mesh` from runtime.yaml, creates MeshManager/LeaderElector when enabled, starts gossip/heartbeat background loops
- `PeerClient` extended with `from_mesh()` classmethod for dynamic peer discovery
- `cli/main.py` registers `mesh` command group
- `cli/client.py` adds `api_post()` helper

## [0.7.0] - 2026-03-09

### Added

- **ServiceManager** (`astromesh/runtime/services.py`) — controls which subsystems (api, agents, inference, memory, tools, channels, rag, observability) are active on each node
- **PeerClient** (`astromesh/runtime/peers.py`) — HTTP client for inter-node communication with round-robin load balancing, health checks, and request forwarding
- Config profiles for common node roles: `full.yaml`, `gateway.yaml`, `worker.yaml`, `inference.yaml` (`config/profiles/`)
- Conditional bootstrap in AgentRuntime — only initializes subsystems enabled by ServiceManager
- `spec.services` and `spec.peers` configuration sections in `runtime.yaml`
- `astromeshctl peers list` command — display peer nodes with services and connectivity status
- `astromeshctl services` command — display enabled/disabled services on the current node
- Universal multi-stage Dockerfile for all node roles (`Dockerfile`)
- Docker Compose mesh configuration for multi-node local development: gateway + worker + inference nodes (`docker/docker-compose.mesh.yml`)
- `/v1/system/status` now includes `services` (enabled map) and `peers` (list with health)
- `/v1/system/doctor` now checks peer connectivity in addition to local health
- Phase 2 design and implementation plan documents (`docs/plans/2026-03-09-astromesh-os-phase2-*.md`)
- Tests for ServiceManager, PeerClient, conditional bootstrap, mesh integration, CLI commands, and API extensions (7 new test files, 254 total tests passing)

### Changed

- `AgentRuntime` accepts optional `service_manager` and `peer_client` parameters (backward compatible — all services enabled when omitted)
- `daemon/astromeshd.py` parses `spec.services` and `spec.peers` from runtime.yaml, wires into runtime
- `cli/main.py` registers `peers` and `services` command groups

## [0.6.0] - 2026-03-09

### Added

- `astromeshd` daemon — single-process async runtime daemon with systemd integration (`daemon/astromeshd.py`)
- Auto-detection of config directory: `/etc/astromesh/` (system mode) vs `./config/` (dev mode)
- PID file management and graceful shutdown via SIGTERM/SIGHUP signal handling
- systemd notify support via `sdnotify` for `Type=notify` service readiness
- `astromeshctl` CLI management tool built with Typer + Rich (`cli/`)
- CLI `status` command — daemon uptime, version, mode, loaded agents count
- CLI `doctor` command — system health checks with per-provider diagnostics
- CLI `agents list` command — display loaded agents in Rich table
- CLI `providers list` command — display configured model providers
- CLI `config validate` command — offline YAML validation without starting daemon
- All CLI commands support `--json` flag for machine-readable output
- `GET /v1/system/status` API endpoint — version, uptime, mode, PID, agents count
- `GET /v1/system/doctor` API endpoint — runtime and provider health checks
- systemd unit file with security hardening: `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp` (`packaging/systemd/astromeshd.service`)
- Installation script for Linux system deployment: creates `astromesh` user, filesystem layout, permissions (`packaging/install.sh`)
- Filesystem layout convention: `/etc/astromesh/` (config), `/var/lib/astromesh/` (state), `/var/log/astromesh/` (logs), `/opt/astromesh/` (binaries)
- `cli` and `daemon` optional dependency groups in `pyproject.toml`
- `astromeshd` and `astromeshctl` console script entry points
- Design documents for Astromesh OS phases 1-4 (`docs/plans/2026-03-09-astromesh-os-*.md`)
- Tests for daemon, CLI, system API, and integration (4 new test files)

### Changed

- Registered system routes in FastAPI app (`astromesh/api/main.py`)

## [0.5.0] - 2026-03-09

### Added

- Production-grade Helm chart for Kubernetes deployment (`deploy/helm/astromesh/`)
- Helm chart core: Deployment, Service, Ingress, HPA, ConfigMaps, Secrets, ServiceAccount
- Bitnami PostgreSQL and Redis as hybrid subchart dependencies (disableable for external services)
- Ollama as optional subchart for local LLM inference
- vLLM deployment and service templates with GPU scheduling and configurable model/args
- HuggingFace TEI (Text Embeddings Inference) parametrized templates supporting N instances (embeddings, reranker)
- HuggingFace token authentication (`secret-hf-token.yaml`) for gated model downloads
- kube-prometheus-stack and OpenTelemetry Collector as optional observability subcharts
- Auto-wiring of OTel collector endpoint when subchart is enabled (`astromesh.otel.endpoint` helper)
- External Secrets Operator integration with provider-agnostic `SecretStore` and `ExternalSecret` templates
- ArgoCD `ApplicationSet` for automated multi-environment GitOps deployment (`deploy/gitops/argocd/`)
- Custom Resource Definitions for future Kubernetes Operator (`deploy/helm/astromesh/crds/`):
  - `agents.astromesh.io` — Agent lifecycle management
  - `providers.astromesh.io` — LLM provider configuration
  - `channels.astromesh.io` — Channel integration management
  - `ragpipelines.astromesh.io` — RAG pipeline configuration
- Environment-specific values profiles: `values-dev.yaml`, `values-staging.yaml`, `values-prod.yaml`
- Comprehensive Kubernetes deployment guide (`docs/KUBERNETES_DEPLOYMENT.md`)
- Design documents for all 6 implementation phases (`docs/plans/2026-03-09-*.md`)

### Changed

- Updated `.gitignore` with Helm subchart tarball exclusion (`deploy/helm/astromesh/charts/*.tgz`)

## [0.4.0] - 2026-03-08

### Added

- Rust native extensions (`astromesh._native`) via PyO3 for CPU-bound hot paths (5-50x speedup)
- `native/src/chunking.rs` — Fixed, Recursive, Sentence chunkers with zero-copy UTF-8 slicing + cosine similarity + semantic grouping
- `native/src/guardrails.rs` — `RustPiiRedactor` with pre-compiled regex (email, phone, SSN, CC) + `RustTopicFilter` using Aho-Corasick single-pass automaton
- `native/src/tokens.rs` — `RustTokenBudget` for fast token budget selection with `split_whitespace` fallback
- `native/src/ratelimit.rs` — `RustRateLimiter` with `VecDeque` sliding window (O(1) cleanup vs O(n) in Python)
- `native/src/routing.rs` — `rust_ema_update`, `rust_detect_vision`, `rust_rank_candidates` helpers for model routing
- `native/src/cost_tracker.rs` — `RustCostIndex` with indexed cost/usage queries and `group_by` aggregation
- `native/src/json_parser.rs` — `rust_json_loads` using serde_json for fast JSON → Python object conversion
- Automatic fallback to pure Python when Rust extensions are not compiled (`try/except ImportError`)
- `ASTROMESH_FORCE_PYTHON=1` env var to disable native extensions at runtime
- Parametrized test fixture (`use_native`) for testing both native and Python backends
- Correctness tests for all native modules (`tests/test_native_*.py`)
- Benchmark suite (`tests/benchmarks/`) comparing native vs Python for chunking, guardrails, tokens, rate limiting, routing, cost tracking, and JSON parsing
- `pytest-benchmark>=4.0` dev dependency
- `[tool.maturin]` configuration in `pyproject.toml` for building native extensions
- Native extensions documentation (`docs/NATIVE_ESTENSIONS_RUST.md`)
- `LICENSE.md` — MIT license
- `SECURITY.md` — security policy and vulnerability reporting guidelines
- `CODE_OF_CONDUCT.md` — contributor code of conduct
- `CONTRIBUTING.md` — contribution guidelines
- `GOVERNANCE.md` — project governance model
- `NOTICE.md` — third-party notices
- Project logo (`assets/astromesh-logo.png`)

### Changed

- `astromesh/rag/chunking/{fixed,recursive,sentence,semantic}.py` — delegate to Rust when available
- `astromesh/core/guardrails.py` — delegate PII redaction and topic filtering to Rust when available
- `astromesh/memory/strategies/token_budget.py` — delegate to `RustTokenBudget` when available
- `astromesh/core/tools.py` — delegate rate limiting to `RustRateLimiter` when available
- `astromesh/core/model_router.py` — delegate vision detection and EMA updates to Rust when available
- `astromesh/observability/cost_tracker.py` — mirror records to `RustCostIndex` for indexed queries
- `astromesh/orchestration/patterns.py` — use `rust_json_loads` for JSON parsing in orchestration loops
- Updated `README.md` with Rust Native Extensions section
- Updated `CLAUDE.md` with `maturin develop` and `cargo test` commands
- Updated `.gitignore` with Rust build artifacts (`target/`, `*.so`, `*.pyd`, `*.dylib`)
- Updated `README.md` with project logo

## [0.3.0] - 2026-03-07

### Added

- Base channel abstraction (`ChannelAdapter`, `ChannelMessage`, `MediaAttachment`) for multi-channel support
- Multimedia message handling: images, audio, video, and documents from WhatsApp
- Media-to-LLM content builder (`build_multimodal_query`) with OpenAI vision format output
- Vision auto-detection in `ModelRouter` — automatically routes multimodal queries to vision-capable providers
- Ollama provider multimodal support — converts OpenAI image format to Ollama's native `images` field
- `WhatsAppClient.download_media()` for fetching media via Meta Graph API
- Channel base tests (`tests/test_channels.py`)

### Changed

- `WhatsAppClient` now extends `ChannelAdapter` abstract base class
- Agent pipeline (`AgentRuntime`, orchestration patterns) accepts `str | list[dict]` queries
- `ModelRouter.route()` auto-detects vision requirements from message content
- WhatsApp webhook route uses `ChannelMessage` and `build_multimodal_query` for media processing
- Memory persistence extracts text from multimodal queries for storage, keeps full content in metadata
- WhatsApp assistant agent uses `capability_match` routing with `llava:7b` as primary vision model

## [0.2.0] - 2026-03-06

### Added

- WhatsApp channel integration via Meta Business Cloud API
- WhatsApp webhook handler (GET verification + POST incoming messages)
- WhatsAppClient service with signature validation and message sending
- Channel configuration support (`config/channels.yaml`)
- Sample WhatsApp agent (`whatsapp-assistant.agent.yaml`) optimized for conversational messaging
- WhatsApp integration guide (`docs/whatsapp-integration.md`)
- Integration tests for WhatsApp webhook (20 tests)
- Design document for WhatsApp channel architecture

### Changed

- Updated architecture docs with Channel Adapters layer
- Updated configuration guide with channel configuration section
- Updated README with WhatsApp integration feature

## [0.1.0] - 2026-03-06

### Added

- Integration tests for full agent run with tools
- Docker stack and sample agent configs
- Guardrails engine, full API routes, WebSocket streaming
- Observability — OpenTelemetry tracing, Prometheus metrics, cost tracker
- ML model registry with ONNX/PyTorch serving and training pipelines
- MCP client/server and wire into ToolRegistry
- 5 orchestration patterns wired into AgentRuntime
- RAG pipeline with chunking, embeddings, vector stores, and reranking
- Memory backends (Redis, SQLite, PG, pgvector, ChromaDB, Qdrant, FAISS) and strategies
- Agent Runtime Engine with YAML config loading
- ReAct pattern and MemoryManager with 3 memory types
- ToolRegistry and PromptEngine (Jinja2)
- Phase 0 — Model Router, 6 providers, FastAPI skeleton
- ProviderProtocol, CompletionResponse, RoutingStrategy
- Project scaffolding with uv + pyproject.toml

[Unreleased]: https://github.com/monaccode/astromesh/compare/v0.27.0...HEAD
[v0.27.0]: https://github.com/monaccode/astromesh/compare/v0.26.0...v0.27.0
[0.16.1]: https://github.com/monaccode/astromesh/compare/v0.16.0...v0.16.1
[0.16.0]: https://github.com/monaccode/astromesh/compare/v0.15.4...v0.16.0
[0.15.4]: https://github.com/monaccode/astromesh/compare/v0.15.3...v0.15.4
[0.15.3]: https://github.com/monaccode/astromesh/compare/v0.15.2...v0.15.3
[0.15.2]: https://github.com/monaccode/astromesh/compare/v0.15.1...v0.15.2
[0.15.1]: https://github.com/monaccode/astromesh/compare/v0.15.0...v0.15.1
[0.15.0]: https://github.com/monaccode/astromesh/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/monaccode/astromesh/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/monaccode/astromesh/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/monaccode/astromesh/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/monaccode/astromesh/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/monaccode/astromesh-platform/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/monaccode/astromesh-platform/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/monaccode/astromesh-platform/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/monaccode/astromesh-platform/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/monaccode/astromesh-platform/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/monaccode/astromesh-platform/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/monaccode/astromesh-platform/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/monaccode/astromesh-platform/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/monaccode/astromesh-platform/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/monaccode/astromesh-platform/releases/tag/v0.1.0
