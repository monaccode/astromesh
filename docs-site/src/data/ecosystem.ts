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
    blurb: 'Four ways to write an agent — Python, browser, desktop, or plain English. All of them emit the same YAML.',
    accent: '#8b5cf6',
    start: 0,
    sweep: 120,
  },
  {
    id: 'runtime',
    label: 'Execute',
    blurb: 'What the core runs when a loop of tool calls is the wrong shape for the job.',
    accent: '#f472b6',
    start: 120,
    sweep: 30,
  },
  {
    id: 'reach',
    label: 'Reach',
    blurb: 'The gateway between an agent and the person it is talking to, in both directions.',
    accent: '#10b981',
    start: 150,
    sweep: 30,
  },
  {
    id: 'ship',
    label: 'Ship',
    blurb: 'Where the runtime lives: a system service, a sealed appliance, or cloud infrastructure you did not have to write.',
    accent: '#fb923c',
    start: 180,
    sweep: 90,
  },
  {
    id: 'operate',
    label: 'Operate',
    blurb: 'Day two. Who is running what, for which tenant, at what cost.',
    accent: '#f59e0b',
    start: 270,
    sweep: 60,
  },
  {
    id: 'models',
    label: 'Models',
    blurb: 'Upstream of everything: the foundry that trains and publishes the models the runtime routes to.',
    accent: '#e879f9',
    start: 330,
    sweep: 30,
  },
];

export const CORE: Component = {
  id: 'core',
  name: 'Core Runtime',
  short: 'Core',
  group: 'runtime',
  version: '0.40.0',
  released: '2026-08-06',
  tagline:
    'Loads agents from YAML, routes each role to a model, runs the orchestration pattern, and keeps memory, tools and guardrails around it.',
  latest:
    'Builtin tool `send_message`: an agent can reach a person mid-run instead of only answering whoever wrote first.',
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
    version: '0.2.0',
    released: '2026-07-10',
    tagline: 'Write agents as Python decorators, with hot reload and a project CLI.',
    latest: 'Remote execution against a running node, so a local project can drive a deployed runtime.',
    install: 'pip install astromesh-adk',
    href: '/astromesh/adk/introduction/',
  },
  {
    id: 'forge',
    name: 'Astromesh Forge',
    short: 'Forge',
    group: 'author',
    version: '0.24.0',
    released: '2026-06-18',
    tagline: 'Visual agent builder, served by the node itself at /forge. Nothing to install.',
    latest: 'Canvas editor for multi-agent composition alongside the step-by-step wizard.',
    install: 'Open http://localhost:8000/forge',
    href: '/astromesh/forge/introduction/',
  },
  {
    id: 'cortex',
    name: 'Astromesh Cortex',
    short: 'Cortex',
    group: 'author',
    version: '0.19.0',
    released: '2026-08-06',
    tagline: 'Desktop IDE that also connects to every runtime you own — local, cloud, or a managed hub.',
    latest:
      'The operator Admin panel can write: create a tariff, load a plan, assign it to a tenant — no more curl with an operator token.',
    install: 'Download the desktop app',
    href: '/astromesh/cortex/introduction/',
    repo: 'https://github.com/monaccode/astromesh-cortex',
  },
  {
    id: 'leia',
    name: 'Astromesh Leia',
    short: 'Leia',
    group: 'author',
    version: '0.5.0',
    released: '2026-07-29',
    tagline: 'Agent operations in plain English, from inside Claude Code.',
    latest:
      'Knows agent chaining and structured output — including when a chain will silently do nothing, and how to say so.',
    install: '/plugin install astromesh-leia',
    href: '/astromesh/leia/introduction/',
    repo: 'https://github.com/monaccode/astromesh-leia',
  },
  {
    id: 'glyph',
    name: 'Glyph',
    short: 'Glyph',
    group: 'runtime',
    version: '0.1.0',
    released: '2026-08-03',
    tagline: 'An action language: the model writes one program instead of one tool call per turn.',
    latest:
      '`map` can invoke a capability per item in parallel, and a host can bind variables before the program runs.',
    install: 'uv sync --extra glyph',
    href: '/astromesh/glyph/introduction/',
  },
  {
    id: 'herald',
    name: 'Astromesh Herald',
    short: 'Herald',
    group: 'reach',
    version: '0.1.0',
    released: '2026-08-06',
    tagline:
      'Communications gateway. Inbound WhatsApp messages reach an agent; agents reach people back through the same outbox.',
    latest:
      'First release: WhatsApp Cloud API, two-way routing decided by an entry agent, a Postgres outbox with a retry budget, and an embedded operator console.',
    install: 'docker compose -f deploy/docker-compose.yaml up',
    href: '/astromesh/herald/introduction/',
    repo: 'https://github.com/monaccode/astromesh-herald',
  },
  {
    id: 'node',
    name: 'Astromesh Node',
    short: 'Node',
    group: 'ship',
    version: '0.1.1',
    released: '2026-07-13',
    tagline: 'Installs the runtime as a native system service on Linux, macOS and Windows.',
    latest: 'Signed .deb and .rpm packages, plus a Windows service installer.',
    install: 'sudo apt install ./astromesh_<version>_amd64.deb',
    href: '/astromesh/node/introduction/',
  },
  {
    id: 'os',
    name: 'Astromesh OS',
    short: 'OS',
    group: 'ship',
    version: '0.10.1',
    released: '2026-07-29',
    tagline: 'Immutable, API-only Linux appliance. A/B slots, so an update that will not boot rolls back.',
    latest: 'A boot gate in CI: an image that imports but does not start never becomes a release.',
    install: 'Flash the published .raw image',
    href: '/astromesh/os/introduction/',
    repo: 'https://github.com/monaccode/astromesh-os',
  },
  {
    id: 'prisma',
    name: 'Astromesh Prisma',
    short: 'Prisma',
    group: 'ship',
    version: '0.1.0',
    released: '2026-07-17',
    tagline:
      'Reconciles the same agent spec into each cloud’s own managed AI primitives — and writes down what a cloud cannot host.',
    latest:
      'Agent, memory, RAG, tools and guardrails mapped onto the researched GCP surface. Everything still runs against an in-memory gateway.',
    install: 'uv sync --extra dev',
    href: '/astromesh/prisma/introduction/',
    repo: 'https://github.com/monaccode/astromesh-prisma',
    inDevelopment: true,
  },
  {
    id: 'orbit',
    name: 'Astromesh Orbit',
    short: 'Orbit',
    group: 'ship',
    version: '0.4.0',
    released: '2026-07-14',
    tagline: 'One command turns a config file into a production GCP stack — and ejects to raw Terraform whenever you want out.',
    latest: 'Observability: a Cloud Monitoring dashboard, an OTel collector sidecar exporting to Cloud Trace, and `orbit logs`.',
    install: 'pip install astromesh-orbit[gcp]',
    href: '/astromesh/orbit/introduction/',
  },
  {
    id: 'nexus',
    name: 'Astromesh Nexus',
    short: 'Nexus',
    group: 'operate',
    version: '0.11.0',
    released: '2026-08-06',
    tagline: 'Multi-tenant control plane: publishes agents, dispatches runs to a shared pool, meters and bills them.',
    latest:
      'Per-run credentials — Nexus mints a short-lived token per invocation, so an agent can send a message without the shared pool holding any tenant secret.',
    install: 'kubectl apply -k deploy/overlays/mvp',
    href: '/astromesh/nexus/introduction/',
    repo: 'https://github.com/monaccode/astromesh-nexus',
  },
  {
    id: 'cli',
    name: 'astromeshctl',
    short: 'CLI',
    group: 'operate',
    version: '0.2.0',
    released: '2026-07-25',
    tagline: 'The terminal interface to a node: agents, config, mesh state, profiles.',
    latest: 'Profiles, so one CLI talks to several nodes without re-typing a URL and a key.',
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
