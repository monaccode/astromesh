---
title: Astromesh OS (Appliance)
description: Deploy Astromesh as a minimal, immutable, API-only Linux appliance.
---

**Astromesh OS** is a minimal, immutable, **API-only Linux appliance** that exists for one purpose: running Astromesh agents. It is built with `mkosi` on Debian, ships a verified read-only root (dm-verity), updates via A/B slots with automatic rollback, and bakes the runtime in at a pinned commit — no shell, no SSH, no package manager at runtime.

👉 **Full documentation has moved to its own section: [Astromesh OS](/astromesh/os/introduction/).**

- [Introduction](/astromesh/os/introduction/) — what the appliance is and why
- [Architecture](/astromesh/os/architecture/) — immutability, A/B updates, UKI, the 500 MB ceiling
- [Building the Image](/astromesh/os/building/) — mkosi, the WSL2 + KVM dev loop, and CI
- [Phases & Roadmap](/astromesh/os/roadmap/) — the gated path from Phase 0 to fleet

## Not what you were looking for?

Astromesh OS is a **self-contained appliance image**. If instead you want to install the runtime as a **system service** on an existing Linux, macOS, or Windows machine (via `.deb` / `.rpm` / installer), you want **[Astromesh Node](/astromesh/node/introduction/)** — the cross-platform installer and daemon. See [The Ecosystem](/astromesh/getting-started/ecosystem/) for how the two differ.
