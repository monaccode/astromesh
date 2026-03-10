# Astromesh Maia -- Developer Guide

> **Protocol internals:** For gossip mechanics, heartbeat thresholds, leader election, and API endpoints, see [ASTROMESH_MAIA.md](ASTROMESH_MAIA.md).

---

## 1. What is Maia?

Maia is Astromesh's gossip-based discovery layer. Instead of listing every peer URL in every node's config (static peers), you point nodes at one or more seed addresses and Maia handles the rest: automatic discovery, failure detection, leader election, and least-connections request routing. See [ASTROMESH_MAIA.md](ASTROMESH_MAIA.md) for the full protocol description.

---

## 2. Quick Start

The fastest way to run a Maia mesh locally is the 3-node recipe.

```bash
# Start the cluster (gateway + worker + inference + supporting services)
docker compose -f recipes/mesh-3node.yml up -d

# Verify all three nodes are visible
curl http://localhost:8000/v1/mesh/state
```

The response should list three nodes with `status: alive`. If a node shows `suspect` or `dead`, give it a few seconds for gossip to converge and retry.

---

## 3. Recipes Reference

| Recipe | File | Use Case |
|--------|------|----------|
| Single Node | `recipes/single-node.yml` | Development, testing, single-machine deployment |
| 3-Node Mesh | `recipes/mesh-3node.yml` | Standard mesh cluster with role separation |
| GPU Mesh | `recipes/mesh-gpu.yml` | Mesh with NVIDIA GPU for local inference |
| Dev Full Stack | `recipes/dev-full.yml` | Full stack with monitoring (Prometheus, Grafana, OTel) |

All recipes are self-contained Compose files. Run any of them with:

```bash
docker compose -f recipes/<file> up -d
```

---

## 4. Environment Variables

These variables control the Docker entrypoint and config generation.

| Variable | Default | Description |
|----------|---------|-------------|
| `ASTROMESH_ROLE` | `full` | Node role: `full`, `gateway`, `worker`, or `inference` |
| `ASTROMESH_MESH_ENABLED` | `false` | Enable Maia gossip discovery |
| `ASTROMESH_NODE_NAME` | `$(hostname)` | Human-readable node name in the mesh cluster |
| `ASTROMESH_SEEDS` | *(empty)* | Comma-separated seed node URLs (e.g. `http://gateway:8000`) |
| `ASTROMESH_PORT` | `8000` | API listen port |
| `ASTROMESH_AUTO_CONFIG` | `true` | Set to `false` to skip config generation and use a mounted config |
| `OPENAI_API_KEY` | *(empty)* | Passed through to the daemon for OpenAI provider |
| `ANTHROPIC_API_KEY` | *(empty)* | Passed through to the daemon for Anthropic provider |

---

## 5. How Config Generation Works

The Docker image's `entrypoint.sh` generates a runtime config automatically on every container start:

1. **Check for opt-out.** If `ASTROMESH_AUTO_CONFIG=false`, the entrypoint skips generation and runs `astromeshd` with the mounted config directly. If no config exists at `/etc/astromesh/runtime.yaml`, it exits with an error.

2. **Select a profile.** The entrypoint picks a profile based on two variables:
   - `ASTROMESH_MESH_ENABLED` -- determines whether to use a mesh or non-mesh profile.
   - `ASTROMESH_ROLE` -- determines which role profile to load.

3. **Patch with environment overrides.** The selected profile is copied to `/etc/astromesh/runtime.yaml` with `ASTROMESH_NODE_NAME`, `ASTROMESH_SEEDS`, and `ASTROMESH_PORT` applied.

4. **Start the daemon.** `exec astromeshd` replaces the entrypoint process.

To bypass all of this and supply your own config, see [Advanced: Custom Config](#7-advanced-custom-config).

---

## 6. Config Profiles

Seven pre-built profiles ship in the Docker image under `/etc/astromesh/profiles/`:

### Non-mesh profiles (static peers)

| Profile | File | Description |
|---------|------|-------------|
| Full | `config/profiles/full.yaml` | All services on a single node (default) |
| Gateway | `config/profiles/gateway.yaml` | API + channels only, no agent execution |
| Worker | `config/profiles/worker.yaml` | Agent execution + tools, no API exposure |
| Inference | `config/profiles/inference.yaml` | LLM serving only (local models) |

### Mesh profiles (Maia gossip)

| Profile | File | Description |
|---------|------|-------------|
| Mesh Gateway | `config/profiles/mesh-gateway.yaml` | Gateway with Maia enabled, `seeds: []` (is the seed) |
| Mesh Worker | `config/profiles/mesh-worker.yaml` | Worker with Maia enabled, seeds to gateway |
| Mesh Inference | `config/profiles/mesh-inference.yaml` | Inference with Maia enabled, seeds to gateway |

### How the entrypoint selects a profile

```
ASTROMESH_MESH_ENABLED=false  →  /etc/astromesh/profiles/{ASTROMESH_ROLE}.yaml
ASTROMESH_MESH_ENABLED=true   →  /etc/astromesh/profiles/mesh-{ASTROMESH_ROLE}.yaml
```

If the computed profile path does not exist (e.g. `ASTROMESH_ROLE=full` with `ASTROMESH_MESH_ENABLED=true` and no `mesh-full.yaml`), the entrypoint exits with an error listing available profiles.

---

## 7. Advanced: Custom Config

Mount your own `runtime.yaml` and disable auto-generation:

```bash
docker run -d \
  -v /path/to/my/runtime.yaml:/etc/astromesh/runtime.yaml:ro \
  -e ASTROMESH_AUTO_CONFIG=false \
  -p 8000:8000 \
  monaccode/astromesh:latest
```

With `ASTROMESH_AUTO_CONFIG=false`, the entrypoint skips profile selection and patching entirely. You are responsible for all settings in your mounted config, including `spec.mesh.node_name`, `spec.mesh.seeds`, and `spec.api.port`.

---

## 8. Advanced: Scaling Workers

Add more workers to a running mesh with Compose `--scale`:

```bash
docker compose -f recipes/mesh-3node.yml up -d --scale worker=3
```

Each new worker container automatically:
- Gets a unique hostname (used as `node_name` by default)
- Contacts the gateway seed via gossip
- Registers its agents and services
- Begins receiving routed requests

No config changes are needed on existing nodes.

---

## 9. Maia vs Static Peers

| | Static Peers | Maia |
|---|---|---|
| **Setup** | List every peer URL on every node | List seed URLs only |
| **Adding a node** | Update config on all existing nodes | New node joins via seeds automatically |
| **Removing a node** | Update config on all existing nodes | Node leaves or times out |
| **Failure detection** | None -- requests to dead peers fail | Automatic (alive -> suspect -> dead) |
| **Routing** | Round-robin across configured peers | Least-connections across alive nodes |
| **Leader election** | None | Automatic (bully algorithm) |

**Use static peers** when you have 2-3 fixed nodes and want zero additional complexity.

**Use Maia** when you need dynamic scaling, failure detection, or more than a handful of nodes.

When Maia is enabled, `spec.peers` is ignored. If both are configured, a warning is logged.

---

## 10. CLI Commands

Use `astromeshctl` to inspect and manage the mesh. In Docker, run commands via `docker exec`:

```bash
# Cluster overview: node count, leader, alive/suspect/dead summary
docker exec astromesh-gateway astromeshctl mesh status

# Detailed table of all nodes: name, URL, services, agents, load, status
docker exec astromesh-gateway astromeshctl mesh nodes

# Gracefully remove this node from the cluster
docker exec astromesh-worker astromeshctl mesh leave
```

These commands talk to the local node's API. You can run them from any node in the cluster.

---

## 11. Troubleshooting

### Nodes not discovering each other

- Verify `ASTROMESH_MESH_ENABLED=true` is set on all nodes.
- Verify `ASTROMESH_SEEDS` points to a reachable seed node URL (e.g. `http://gateway:8000`).
- Check that the seed node is already running before other nodes start. The gateway should start first.
- Confirm containers are on the same Docker network and can resolve each other's hostnames.

### Node stuck in `suspect` or `dead`

- A node marked `suspect` has not sent a heartbeat in 15+ seconds. Check if the node's process is healthy (`docker logs <container>`).
- A node marked `dead` (30+ seconds without heartbeat) is removed from routing. Restart the container to rejoin.
- If all nodes show each other as suspect, there may be a network partition or clock skew between containers.

### Config not generated

- Check that `ASTROMESH_AUTO_CONFIG` is not set to `false` unless you are mounting your own config.
- Check container logs for `[entrypoint] ERROR: Profile not found` -- this means the combination of `ASTROMESH_ROLE` and `ASTROMESH_MESH_ENABLED` does not match an available profile.

### Wrong profile selected

- Run `docker exec <container> cat /etc/astromesh/runtime.yaml` to see the generated config.
- Verify that `ASTROMESH_ROLE` and `ASTROMESH_MESH_ENABLED` are set correctly in your Compose file or `docker run` command.
- Remember: there is no `mesh-full.yaml` profile. If you need a full-service node with Maia, use `gateway` role or create a custom config.
