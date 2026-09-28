---
title: "CLI Reference"
description: "astromeshd flags and the astromeshctl commands Astromesh Node adds"
---

Astromesh Node ships two entry points: the `astromeshd` daemon and `astromeshctl`. `astromeshctl` itself comes from the `astromesh-cli` package; Node registers a plugin on it (the `astromeshctl.plugins` entry point) that adds `init`, `validate`, `config validate` and `centinela`. Everything else — `status`, `doctor`, `agents list`, `providers list`, `run`, `traces`, `mesh`, … — is documented in the [CLI Commands reference](/astromesh/reference/cli-commands/).

`astromeshctl` talks to the daemon over HTTP at `ASTROMESH_DAEMON_URL` (default `http://localhost:8000`). There are no global flags besides `--help`; JSON output is a per-command `--json` flag.

Service control (start, stop, restart, logs) is done with the platform service manager, not with `astromeshctl` — see [Service control](#service-control) below.

## `astromeshd`

| Flag | Default | Description |
|------|---------|-------------|
| `--config DIR` | auto-detected | Config directory. Without it: the system dir if it has a `runtime.yaml`, else `./config` if it has one, else the system dir |
| `--host HOST` | `spec.api.host`, else `0.0.0.0` | Bind address |
| `--port PORT` | `spec.api.port`, else `8000` | Bind port |
| `--log-level LEVEL` | `info` | `debug`, `info`, `warning`, `error` |
| `--pid-file PATH` | `<data dir>/astromeshd.pid` | PID file (`/var/lib/astromesh/astromeshd.pid` on Linux) |
| `--foreground` | off | Run without init-system integration (no systemd notify / watchdog) |

The system config dir is `/etc/astromesh` on Linux, `/Library/Application Support/Astromesh/config` on macOS and `%ProgramData%\Astromesh\config` on Windows.

## `astromeshctl version`

```bash
astromeshctl version
```

```
astromesh-cli 0.3.1
astromesh core 0.59.0
```

## `astromeshctl init`

Interactive wizard. Writes `runtime.yaml` (from the chosen role's profile), `providers.yaml`, a `.env` with the provider API key if you entered one, and copies the sample agents into `agents/`. It then validates what it wrote and prints how to start the daemon.

```bash
sudo astromeshctl init [--role ROLE] [--non-interactive] [--dev]
```

| Flag | Description |
|------|-------------|
| `--role` | Node role: `full`, `gateway`, `worker`, `inference`. Prompted for when omitted |
| `--non-interactive` | Accept all defaults: role `full` (unless `--role`), provider `ollama`, no mesh, overwrite existing files without asking |
| `--dev` | Write to `./config/` instead of the system config dir |

Run as root, `init` writes to `/etc/astromesh/`; as a regular user, on Windows, or with `--dev` it writes to `./config/`. On macOS and Windows the daemon's system directory is elsewhere, so run `init --dev` from `/Library/Application Support/Astromesh` or `C:\ProgramData\Astromesh`. The provider prompt offers `ollama`, `openai`, `anthropic` or `skip`. The mesh prompt appears only for roles other than `full`.

```bash
sudo astromeshctl init --role worker --non-interactive
```

:::caution[Packaged installs]
The wizard looks for its role profiles next to its own source tree. In the `.deb`/`.rpm`/macOS/Windows builds it does not find them, prints `Profile not found` and writes an empty `runtime.yaml` (which runs with every service on — the `full` defaults). On Linux, copy the one the package ships in `/etc/astromesh/profiles/` over it.
:::

## `astromeshctl validate`

Checks every YAML file under a directory: syntax, and that `kind` matches the file name (`*.agent.yaml` → `Agent`, `*.workflow.yaml` → `Workflow`, `providers.yaml` → `ProviderConfig`, `runtime.yaml` → `RuntimeConfig`, `channels.yaml` → `ChannelConfig`).

```bash
astromeshctl validate [--path ./config]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--path` | `./config` | Directory to validate |

## `astromeshctl config validate`

Parses `runtime.yaml`, `providers.yaml`, `channels.yaml`, `agents/*.agent.yaml` (which must be `kind: Agent`) and `rag/*.rag.yaml` in a directory, without starting the daemon.

```bash
astromeshctl config validate [--path ./config]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--path` | `./config` | Config directory to validate |

:::note[Exit code]
`validate` and `config validate` exit `1` when they find an error, and `config validate` also when the directory doesn't exist — so they can gate a CI pipeline. Since astromesh-node **v0.1.6**; earlier versions exit `0` either way.
:::

## `astromeshctl centinela`

Manages the [Centinela](/astromesh/nebula/centinela/) model provider endpoints.

| Command | Flags | Description |
|---------|-------|-------------|
| `centinela reconcile` | `--bindings` (`./config/centinela/bindings.yaml`), `--out` (`./config/providers.centinela.yaml`) | Build the Centinela `ProviderConfig` from the bindings and the vendored catalog lock |
| `centinela plan-promotion` | `--new-lock` (required), `--version` (required), `--bindings`, `--vendored-lock` (`./docs-site/src/data/catalog.lock.json`), `--pr-body` (`./pr-body.md`), `--labels-out` (`./pr-labels.txt`), `--pyproject` (repeatable) | Plan a promotion to a new Nebula catalog (no HF calls): refreshes the vendored lock, bumps the `astromesh-nebula` pin in the given `pyproject.toml` files, appends stub bindings for new models, and writes the PR body and labels |
| `centinela apply-endpoints` | `--bindings`, `--out`, `--namespace` (default `$HF_ORG`), `--dry-run`, `--wait-timeout` (`1800` s) | Create or update the Hugging Face endpoints (needs `HF_TOKEN`) and write the resulting `ProviderConfig` |

Exit codes: `reconcile` exits `1` on a reconcile error; `plan-promotion` exits `2` when planning fails and `1` when the plan has blocked moves; `apply-endpoints` exits `2` when planning fails.

## Service control

| Action | Linux (systemd) | macOS (launchd) | Windows |
|--------|-----------------|-----------------|---------|
| Start | `sudo systemctl start astromeshd` | `sudo launchctl load /Library/LaunchDaemons/com.astromesh.daemon.plist` | `Start-Service astromeshd` |
| Stop | `sudo systemctl stop astromeshd` | `sudo launchctl unload /Library/LaunchDaemons/com.astromesh.daemon.plist` | `Stop-Service astromeshd` |
| Restart | `sudo systemctl restart astromeshd` | unload + load | `Restart-Service astromeshd` |
| Logs | `journalctl -u astromeshd -f` | `/Library/Logs/Astromesh/astromeshd.{out,err}.log` | — |
| Reload agents | `sudo systemctl reload astromeshd` | `sudo launchctl kill HUP system/com.astromesh.daemon` | — (restart) |

`systemctl reload astromeshd` (or `SIGHUP`, on Linux and macOS) reloads **agents and RAG pipelines** from `agents/` and `rag/` without restarting — available since astromesh-node **v0.1.5** (core **v0.60.0**). Everything is rebuilt aside and swapped at once: a cycle between agents or a chain that doesn't compile leaves the running agents untouched; an agent that fails to build goes `draft` with its error (see `astromeshctl agents list`) without taking the others down; a paused agent stays paused. In-flight runs finish on the old agent. `runtime.yaml` (host, port, services, mesh, peers) and `providers.yaml` are **not** reloaded — restart for those; the daemon logs a warning if `runtime.yaml` changed. With `ASTROMESH_PERSIST_AGENTS=0` the reload is refused, because the disk is not where the agents live.
