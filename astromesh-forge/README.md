# Astromesh Forge

Visual agent builder for the Astromesh platform.

## Quick Start

### Standalone

```bash
cd astromesh-forge
npm install
npm run dev
```

Configure the Astromesh node URL via environment variable:

```bash
VITE_ASTROMESH_URL=http://localhost:8000 npm run dev
```

### Embedded (in Astromesh node)

```bash
cd astromesh-forge
npm run build
cp -r dist/ ../astromesh/static/forge/
```

Then access at `http://localhost:8000/forge`.

## Features

- **7-step Wizard** — Create agents step by step (identity, model, tools, orchestration, settings, prompts, review)
- **Visual Canvas** — Drag-and-drop editor with macro view (agent orchestration) and micro view (pipeline drill-down)
- **Templates Gallery** — 15 pre-built agent templates for common business use cases
- **Multi-target Deploy** — Deploy to local node, remote node, or Nexus (coming soon)

## Tech Stack

- Vite + React + TypeScript
- React Flow (canvas)
- dnd-kit (drag & drop)
- Tailwind CSS
- Zustand (state)
- React Router

## Development

```bash
npm run dev       # Dev server with hot reload
npm run build     # Production build
npm run preview   # Preview production build
npx vitest        # Run tests
npx vitest --ui   # Test UI
```
