/**
 * The Astromesh component registry.
 *
 * Single source for the homepage star chart (EcosystemMap), the release
 * ledger (ReleaseRadar) and anything else that needs to name a component.
 * Versions are literals on purpose: the sibling repos (Cortex, Nexus, Herald,
 * Leia, Nebula, OS) are not on disk when this site builds, so reading them
 * would only work on one machine. Update them here when a release ships.
 */

export type GroupId = 'author' | 'runtime' | 'reach' | 'ship' | 'operate' | 'models';

export interface Group {
  id: GroupId;
  /** Rim label on the chart and the tab label. */
  label: string;
  /** What this slice of the stack is for, in the reader's terms. */
  blurb: string;
  accent: string;
  /** Sector start angle, degrees clockwise from the top of the chart. */
  start: number;
  /**
   * Sector sweep in degrees. The six sweeps total 360°, so a group that grows
   * packs its members tighter rather than pushing the next sector around the
   * rim — `angleOf` divides the sweep by however many members there are.
   */
  sweep: number;
}

export interface Component {
  id: string;
  name: string;
  /** Short form for the chart chip, where 96px is all there is. */
  short: string;
  group: GroupId;
  version: string;
  /** Release date of `version`, ISO. */
  released: string;
  /** What it does, one line, in the reader's terms. */
  tagline: string;
  /** What landed in `version`. One sentence, no marketing. */
  latest: string;
  /** How you install or get it. */
  install: string;
  href: string;
  /** Set when the component lives in its own repository. */
  repo?: string;
  /**
   * Set when the component is on the map but has not shipped. It is drawn and
   * listed like the rest; every surface that shows it says so rather than
   * letting a version number imply something you can install.
   */
  inDevelopment?: boolean;
}

/** Clockwise from the top: you author, it runs, it reaches people, you ship it, you operate it, and the models come from somewhere. */
export const GROUPS: Group[] = [
  {
    id: 'author',
    label: 'Author',
    blurb: 'Four ways to write an agent — Python, browser, desktop, or plain English — all emitting the same YAML, and a spec-first method for building software with coding agents.',
    accent: '#8b5cf6',
    start: 0,
    sweep: 103,
  },
  {
    id: 'runtime',
    label: 'Execute',
    blurb: 'What runs around the model: an action language for when a loop of tool calls is the wrong shape, and libraries that put the right knowledge in front of it.',
    accent: '#f472b6',
    start: 103,
    sweep: 78,
  },
  {
    id: 'reach',
    label: 'Reach',
    blurb: 'How an agent reaches out: a gateway to the person it is talking to, in both directions, and a protocol to agents running on someone else’s stack.',
    accent: '#10b981',
    start: 181,
    sweep: 40,
  },
  {
    id: 'ship',
    label: 'Ship',
    blurb: 'Where the runtime lives: a system service, a sealed appliance, or cloud infrastructure you did not have to write.',
    accent: '#fb923c',
    start: 221,
    sweep: 75,
  },
  {
    id: 'operate',
    label: 'Operate',
    blurb: 'Day two. Who is running what, for which tenant, at what cost.',
    accent: '#f59e0b',
    start: 296,
    sweep: 40,
  },
  {
    id: 'models',
    label: 'Models',
    blurb: 'Upstream of everything: the foundry that trains and publishes the models the runtime routes to.',
    accent: '#e879f9',
    start: 336,
    sweep: 24,
  },
];

export const CORE: Component = {
  id: 'core',
  name: 'Core Runtime',
  short: 'Core',
  group: 'runtime',
  version: '0.74.1',
  released: '2026-10-20',
  tagline:
    'Loads agents from YAML, routes each role to a model, runs the orchestration pattern, and keeps memory, tools and guardrails around it.',
    latest: 'Tools `type: a2a` call a remote A2A agent through `astromesh-a2a` (extra `astromesh[a2a]`): only the `card_url` host is reachable, the remote’s output reaches the model wrapped as untrusted, an `input_required` stays pending per session, and the tool always runs as an agent turn. Since 0.73, `origen` (`humano`|`agente`) on run and WebSocket — an agent turn never confirms a `confirm`-gated tool — and `spec.skills` for Agent Cards. 0.74.1 uses the public helpers of `astromesh-a2a` 0.1.1, with no change in behaviour.',
  install: 'pip install astromesh',
  href: '/astromesh/getting-started/what-is-astromesh/',
};

/** Ordered by sector, then by position within the sector. */
export const COMPONENTS: Component[] = [
  {
    id: 'adk',
    name: 'Astromesh ADK',
    short: 'ADK',
    group: 'author',
    version: '0.7.1',
    released: '2026-10-20',
    tagline: 'Write agents as Python decorators, with hot reload and a project CLI.',
    latest: '`remote_a2a()` uses any A2A agent like an ADK agent — `run()`, `stream()`, `as_tool()` — over `astromesh-a2a` (extra `astromesh-adk[a2a]`), always as an agent turn. Remote calls through `bind()`/`connect()`/`remote()` now declare `origen: "agente"`, so a remote node never takes the parent model’s "si" as a human confirmation. 0.7.1: `remote_a2a()` passes the task’s `context_id` when it replies to a pending task.',
    install: 'pip install astromesh-adk',
    href: '/astromesh/adk/introduction/',
  },
  {
    id: 'forge',
    name: 'Astromesh Forge',
    short: 'Forge',
    group: 'author',
    version: '0.29.1',
    released: '2026-10-22',
    tagline: 'Visual agent builder, served by the node itself at /forge. Nothing to install.',
    latest: 'Creates and edits `type: a2a` tools: card URL, auth as an environment variable name (never the secret), optional policy and description, validated with the same limits as the runtime so it never writes YAML that leaves the agent in draft.',
    install: 'Open http://localhost:8000/forge',
    href: '/astromesh/forge/introduction/',
  },
  {
    id: 'cortex',
    name: 'Astromesh Cortex',
    short: 'Cortex',
    group: 'author',
    version: '0.29.0',
    released: '2026-10-22',
    tagline: 'Desktop IDE that also connects to every runtime you own — local, cloud, or a managed hub.',
    latest: 'A2A panel on Nexus agents: the Agent Card a caller sees, or why there is none. Since 0.28, schema at parity with core 0.74.1: `type: a2a` tools with a form that validates like the core, and an A2A block for `spec.a2a.publicar`, the card description and `spec.skills`.',
    install: 'git clone …/astromesh-cortex && npm install && npm run dev',
    href: '/astromesh/cortex/introduction/',
    repo: 'https://github.com/monaccode/astromesh-cortex',
  },
  {
    id: 'leia',
    name: 'Astromesh Leia',
    short: 'Leia',
    group: 'author',
    version: '0.11.1',
    released: '2026-10-26',
    tagline: 'Agent operations in plain English, from inside Claude Code.',
    latest: 'Knows the whole published ecosystem — a request-to-component table (Spanish or English) covering Cortex 0.29, Forge 0.29.1, Glyph, Orbit vs. Prisma (in development) and Nebula/Centinela (preview) — and maps Spanish verbs to its intents. Since 0.10, synced to core 0.74.1 and Nexus 0.28.2: designs `type: a2a` tools, publishes agents over A2A (`spec.a2a.publicar` + `spec.skills`) and checks the Agent Card after deploy; knows the rest of the ecosystem (`astromesh-a2a`, `-okf`, `-rag`, `-context`, ADK 0.7, Herald 0.12).',
    install: 'claude --plugin-dir ./astromesh-leia',
    href: '/astromesh/leia/introduction/',
    repo: 'https://github.com/monaccode/astromesh-leia',
  },  {
    id: 'sdd',
    name: 'Astromesh SDD',
    short: 'SDD',
    group: 'author',
    version: '0.1.0',
    released: '2026-10-13',
    tagline:
      'Spec-Driven Development for any coding agent: spec, plan, tasks, code and verification, each phase a file next to your code.',
    latest:
      'First release: seven Agent Skills, a Claude Code plugin, installers for Claude Code and the `.agents/skills` agents (Codex, OpenCode, Kimi, Gemini, Copilot), and `.sdd/` settings to customize them.',
    install: '/plugin marketplace add monaccode/astromesh-sdd',
    href: '/astromesh/sdd/introduction/',
    repo: 'https://github.com/monaccode/astromesh-sdd',
  },

  {
    id: 'glyph',
    name: 'Glyph',
    short: 'Glyph',
    group: 'runtime',
    version: '0.1.3',
    released: '2026-09-27',
    tagline: 'An action language: the model writes one program instead of one tool call per turn.',
    latest: 'Release aligned with the astromesh 0.59.0 round; still no runtime dependencies.',
    install: 'uv sync --extra glyph',
    href: '/astromesh/glyph/introduction/',
  },
  {
    id: 'okf',
    name: 'Astromesh OKF',
    short: 'OKF',
    group: 'runtime',
    version: '0.1.0',
    released: '2026-10-13',
    tagline:
      'Agents in any framework navigate an Open Knowledge Format bundle — index, concept, links — with trust and freshness signals.',
    latest:
      'First release: the core reader ported from the runtime, plus adapters for LangChain/LangGraph, CrewAI, Google ADK, OpenAI Agents SDK, PydanticAI, LlamaIndex, smolagents, Microsoft Agent Framework and an MCP server, on PyPI.',
    install: 'pip install astromesh-okf',
    href: '/astromesh/okf/introduction/',
    repo: 'https://github.com/monaccode/astromesh-okf',
  },
  {
    id: 'rag',
    name: 'Astromesh RAG',
    short: 'RAG',
    group: 'runtime',
    version: '0.1.0',
    released: '2026-10-14',
    tagline:
      'Retrieval-augmented generation from small, swappable parts: ingest, retrieve, rank and build the context, with naive, hybrid, multi_query or hyde, in Python or YAML.',
    latest:
      'First release: four retrieval patterns with optional reranking, memory, FAISS, Chroma, Qdrant and pgvector indexes, `kind: RAGPipeline` YAML, a trace per query, retrieval metrics and a labeled benchmark corpus. Tagged on GitHub and on PyPI.',
    install: 'pip install astromesh-rag',
    href: '/astromesh/rag/introduction/',
    repo: 'https://github.com/monaccode/astromesh-rag',
  },
  {
    id: 'context',
    name: 'Astromesh Context',
    short: 'Context',
    group: 'runtime',
    version: '0.1.0',
    released: '2026-10-20',
    tagline:
      'Decides what goes into the model’s window — knowledge, memory, history — within one token budget, with a trace per item and an eval that measures the choice.',
    latest:
      'Engine that fills one budget across sources and returns a trace per item; three policies; containment dedupe that inherits OKF deprecation; Compactor and Offloader for the agent loop; ContextEval with a published level-1 table; LangChain, PydanticAI and MCP integrations.',
    install: 'pip install astromesh-context',
    href: '/astromesh/context/introduction/',
    repo: 'https://github.com/monaccode/astromesh-context',
  },
  {
    id: 'herald',
    name: 'Astromesh Herald',
    short: 'Herald',
    group: 'reach',
    version: '0.13.0',
    released: '2026-10-25',
    tagline:
      'Communications gateway. WhatsApp, Telegram, Instagram, Messenger and web chat messages reach an agent behind Nexus; agents reach people back through one outbox.',
    latest:
      'New conversations per day, hour and channel for an owner’s dashboard (`GET /admin/stats/conversaciones`, in the tenant’s time zone, up to 62 days), with zone data embedded in the binary. Since 0.12, Messenger is the fourth Meta channel.',
    install: 'docker compose -f deploy/docker-compose.yaml up',
    href: '/astromesh/herald/introduction/',
    repo: 'https://github.com/monaccode/astromesh-herald',
  },
  {
    id: 'a2a',
    name: 'Astromesh A2A',
    short: 'A2A',
    group: 'reach',
    version: '0.1.1',
    released: '2026-10-20',
    tagline:
      'Lets an agent call, and be called by, agents on any framework over A2A 1.0 — without trusting them: allowlist, size and time caps, untrusted-output wrapping.',
    latest:
      'First release: `RemoteAgent` client and `serve`/`create_app` server on the official A2A SDK, a pinned egress guard, `Policy` with budgets and signed cards, tools for nine frameworks (MCP included), a redacted trace per call and a nine-trap attack eval in CI. On PyPI. 0.1.1 adds the task API (`submit`, `get_task`, `subscribe`, `list_tasks`), `reply(..., context_id=)` and the public `tool_description` and `PENDING_NOTE`.',
    install: 'pip install astromesh-a2a',
    href: '/astromesh/a2a/introduction/',
    repo: 'https://github.com/monaccode/astromesh-a2a',
  },
  {
    id: 'node',
    name: 'Astromesh Node',
    short: 'Node',
    group: 'ship',
    version: '0.1.10',
    released: '2026-09-28',
    tagline: 'Installs the runtime as a native system service on Linux, macOS and Windows.',
    latest: 'A macOS tarball for Intel Macs alongside Apple silicon; every package carries its own CPython and is installed and run on a clean machine before it is published.',
    install: 'sudo apt install ./astromesh-node_<version>_amd64.deb',
    href: '/astromesh/node/introduction/',
  },
  {
    id: 'os',
    name: 'Astromesh OS',
    short: 'OS',
    group: 'ship',
    version: '0.13.8',
    released: '2026-10-17',
    tagline: 'Immutable, API-only Linux appliance. A/B slots, so an update that will not boot rolls back.',
    latest: 'Runtime at core v0.71.0 (permissions, semantic/episodic memory, swarm and `timeout_seconds` now applied), still with its own CPython and no system python3. The boot gate passes on the new pin.',
    install: 'Flash the published .raw image',
    href: '/astromesh/os/introduction/',
    repo: 'https://github.com/monaccode/astromesh-os',
  },
  {
    id: 'prisma',
    name: 'Astromesh Prisma',
    short: 'Prisma',
    group: 'ship',
    version: '0.2.1',
    released: '2026-09-29',
    tagline:
      'Turns your agent into the cloud’s own native agent, on that cloud’s base resources — and writes down what does not carry over.',
    latest:
      'An agent becomes an ADK agent config on Agent Engine, bound to Sessions, Memory Bank, the RAG corpus and Model Armor, with every gap reported. Translates and reconciles against an in-memory gateway; nothing is provisioned yet, and it is not on PyPI.',
    install: 'uv sync && uv run uvicorn astromesh_prisma.app:app',
    href: '/astromesh/prisma/introduction/',
    repo: 'https://github.com/monaccode/astromesh-prisma',
    inDevelopment: true,
  },
  {
    id: 'orbit',
    name: 'Astromesh Orbit',
    short: 'Orbit',
    group: 'ship',
    version: '0.4.4',
    released: '2026-09-28',
    tagline: 'One command turns a config file into a production GCP stack — and ejects to raw Terraform whenever you want out.',
    latest: '`orbit apply` asks before creating billable resources (skip with `--auto-approve`), and `orbit init --provider/--preset` answer the wizard.',
    install: 'pip install astromesh-orbit[gcp]',
    href: '/astromesh/orbit/introduction/',
  },
  {
    id: 'nexus',
    name: 'Astromesh Nexus',
    short: 'Nexus',
    group: 'operate',
    version: '0.28.2',
    released: '2026-10-20',
    tagline: 'Multi-tenant control plane: publishes agents, dispatches runs to a shared pool, meters and bills them.',
    latest:
      'Published agents are served over A2A 1.0 (opt-in with `spec.a2a.publicar: true`): Agent Card and JSON-RPC behind the tenant’s API key or JWT, blocking, streaming and background (`returnImmediately`) runs, `GetTask`, `CancelTask` across replicas, `SubscribeToTask`, `ListTasks` and signed push notifications (off by default). Every A2A run is an agent turn and is billed like any invocation. The runtime pool runs core 0.74.1, so published agents can call remote A2A agents as tools. A completed A2A run carries its usage (tokens and Nexus credits) as a final data part.',
    install: 'kubectl apply -k deploy/overlays/mvp',
    href: '/astromesh/nexus/introduction/',
    repo: 'https://github.com/monaccode/astromesh-nexus',
  },
  {
    id: 'cli',
    name: 'astromeshctl',
    short: 'CLI',
    group: 'operate',
    version: '0.4.1',
    released: '2026-10-17',
    tagline: 'The terminal interface to a node: agents, config, mesh state, profiles.',
    latest: 'The `new agent` template emits `timeout_seconds: 120`: on core 0.71 the old `timeout: 30` cut every run at 30 s. Requires core 0.71. Since 0.4.0, `astromeshctl eval` and the BLOCKED panel in `run`.',
    install: 'pip install astromesh-cli',
    href: '/astromesh/reference/cli-commands/',
  },
  {
    id: 'nebula',
    name: 'Astromesh Nebula',
    short: 'Nebula',
    group: 'models',
    version: '0.1.0',
    released: '2026-06-09',
    tagline: 'The open-model foundry: trains, gates and publishes the models this ecosystem routes to.',
    latest: 'The Foundry pipeline and the GitOps catalog, with Centinela as the first model through it.',
    install: 'See the model catalog',
    href: '/astromesh/nebula/introduction/',
    repo: 'https://github.com/monaccode/astromesh-nebula',
  },
];

/** Everything, core first — for the release ledger. */
export const ALL: Component[] = [CORE, ...COMPONENTS];

// ── Chart geometry ────────────────────────────────────────────────
// A 1000×1000 viewBox. 0° is the top of the chart, angles run clockwise.
// Satellites sit on one ring; the sector they land in is their group, so
// the rim of the chart and the tab bar are the same taxonomy.

export const RING = 370;
export const RIM = 432;
export const LABEL_RING = 466;
export const CORE_R = 96;

export const point = (r: number, deg: number): [number, number] => {
  const a = ((deg - 90) * Math.PI) / 180;
  return [500 + r * Math.cos(a), 500 + r * Math.sin(a)];
};

/** SVG arc path between two angles. `flip` reverses it so text stays upright. */
export const arcPath = (r: number, from: number, to: number, flip = false): string => {
  const [a0, a1, sweep] = flip ? [to, from, 0] : [from, to, 1];
  const [x0, y0] = point(r, a0);
  const [x1, y1] = point(r, a1);
  const large = Math.abs(to - from) > 180 ? 1 : 0;
  return `M ${x0.toFixed(1)} ${y0.toFixed(1)} A ${r} ${r} 0 ${large} ${sweep} ${x1.toFixed(1)} ${y1.toFixed(1)}`;
};

/** A sector whose middle points at the bottom half would render its label upside down. */
export const isFlipped = (g: Group): boolean => {
  const mid = g.start + g.sweep / 2;
  return mid > 90 && mid < 270;
};

/** Angle of a component on the ring, from its position inside its sector. */
export const angleOf = (c: Component): number => {
  const g = GROUPS.find((x) => x.id === c.group)!;
  const members = COMPONENTS.filter((x) => x.group === g.id);
  const i = members.indexOf(c);
  return g.start + ((i + 0.5) * g.sweep) / members.length;
};
