---
title: "Docker Single Node"
description: "Deploy with the pre-built Docker image"
---

This guide covers deploying Astromesh as a single Docker container or with Docker Compose, using the pre-built image. No source code checkout is required.

## What and Why

The Docker single-node deployment packages Astromesh into a container that starts with sensible defaults and can be configured entirely through environment variables and volume mounts. This is the right choice when you want:

- A containerized deployment without Kubernetes complexity
- Quick setup with no build step
- Isolated runtime with reproducible behavior
- Easy integration with existing Docker infrastructure

## Prerequisites

| Requirement | Version | Check command |
|-------------|---------|---------------|
| Docker | 24.0+ | `docker --version` |
| Docker Compose | v2.20+ | `docker compose version` |
| Network | Outbound to LLM provider or local Ollama | -- |

## Step-by-step Setup

### 1. Create a project directory

```bash
mkdir astromesh-deploy && cd astromesh-deploy
```

### 2. Create a Docker Compose file

Create `docker-compose.yml`:

```yaml
# Astromesh Single-Node Deployment
services:
  astromesh:
    image: ghcr.io/monaccode/astromesh:0.10.0
    ports:
      - "8000:8000"
    environment:
      - ASTROMESH_ROLE=full
      - OLLAMA_HOST=http://ollama:11434
    depends_on:
      ollama:
        condition: service_started
    volumes:
      - astromesh-data:/var/lib/astromesh
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama-models:/root/.ollama
    restart: unless-stopped

volumes:
  astromesh-data:
  ollama-models:
```

### 3. Start the stack

```bash
docker compose up -d
```

Expected output:

```
[+] Running 3/3
 ✔ Network astromesh-deploy_default     Created
 ✔ Container astromesh-deploy-ollama-1  Started
 ✔ Container astromesh-deploy-astromesh-1  Started
```

### 4. Pull a model into Ollama

```bash
docker compose exec ollama ollama pull llama3.1:8b
```

Expected output:

```
pulling manifest...
pulling 8eeb52dfb3bb... 100% |████████████████████| 4.7 GB
verifying sha256 digest
writing manifest
success
```

### 5. Verify

```bash
curl http://localhost:8000/health
```

Expected output:

```json
{
  "status": "healthy",
  "version": "0.10.0"
}
```

## Configuration

### Environment variables

The Astromesh container image includes an entrypoint that generates configuration from environment variables at startup. This means you can configure the entire runtime without mounting config files.

| Variable | Default | Description |
|----------|---------|-------------|
| `ASTROMESH_ROLE` | `full` | Service profile: `full`, `gateway`, `worker`, `inference` |
| `ASTROMESH_PORT` | `8000` | API server port |
| `ASTROMESH_LOG_LEVEL` | `info` | Log level: `debug`, `info`, `warning`, `error` |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint URL |
| `OPENAI_API_KEY` | -- | OpenAI API key |
| `OPENAI_ENDPOINT` | `https://api.openai.com/v1` | OpenAI-compatible endpoint |
| `DATABASE_URL` | -- | PostgreSQL connection string |
| `REDIS_URL` | -- | Redis connection string |
| `ASTROMESH_AUTO_CONFIG` | `true` | Generate config from env vars on startup |

### Entrypoint config generation

When `ASTROMESH_AUTO_CONFIG=true` (the default), the container entrypoint:

1. Reads `ASTROMESH_ROLE` to select which services to enable
2. Detects provider env vars (`OLLAMA_HOST`, `OPENAI_API_KEY`) and generates `providers.yaml`
3. Generates `runtime.yaml` with the selected profile
4. Starts `astromeshd` with the generated config

This means a minimal deployment needs only `ASTROMESH_ROLE` and a provider connection.

### Adding providers via environment variables

**Ollama:**

```yaml
environment:
  - OLLAMA_HOST=http://ollama:11434
```

**OpenAI:**

```yaml
environment:
  - OPENAI_API_KEY=sk-...
```

**Both (with fallback):**

```yaml
environment:
  - OLLAMA_HOST=http://ollama:11434
  - OPENAI_API_KEY=sk-...
```

When both are configured, Astromesh uses the model router's `cost_optimized` strategy by default, preferring the local Ollama provider and falling back to OpenAI.

### Custom agents (volume mount)

To deploy your own agent definitions, mount a directory of YAML files:

```yaml
services:
  astromesh:
    image: ghcr.io/monaccode/astromesh:0.10.0
    volumes:
      - ./agents:/etc/astromesh/agents:ro
    environment:
      - ASTROMESH_ROLE=full
      - OLLAMA_HOST=http://ollama:11434
```

Create `agents/support-agent.agent.yaml`:

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: support-agent
  namespace: default
spec:
  identity:
    display_name: "Support Agent"
    description: "Handles customer support queries"
  model:
    primary:
      provider: ollama
      model: llama3.1:8b
    routing:
      strategy: cost_optimized
  prompts:
    system: |
      You are a helpful support agent. Answer questions clearly and concisely.
  orchestration:
    pattern: react
    max_iterations: 5
    timeout_seconds: 30
```

### Ollama connection

When running Ollama as a sibling container, use the Docker service name as the host:

```yaml
environment:
  - OLLAMA_HOST=http://ollama:11434
```

When using Ollama running on the host machine:

```yaml
environment:
  - OLLAMA_HOST=http://host.docker.internal:11434
```

### Persistent data

Use Docker volumes to persist data across container restarts:

```yaml
volumes:
  - astromesh-data:/var/lib/astromesh    # Memory DBs, FAISS indices
  - ollama-models:/root/.ollama          # Downloaded models
```

### Custom config (advanced)

For full control, mount your own configuration files and disable auto-generation:

```yaml
services:
  astromesh:
    image: ghcr.io/monaccode/astromesh:0.10.0
    volumes:
      - ./config/runtime.yaml:/etc/astromesh/runtime.yaml:ro
      - ./config/providers.yaml:/etc/astromesh/providers.yaml:ro
      - ./config/channels.yaml:/etc/astromesh/channels.yaml:ro
      - ./config/agents:/etc/astromesh/agents:ro
    environment:
      - ASTROMESH_AUTO_CONFIG=false
      - OPENAI_API_KEY=sk-...
```

When `ASTROMESH_AUTO_CONFIG=false`, the entrypoint skips config generation and starts the daemon directly with the mounted files.

## Full stack with infrastructure

For a complete deployment with PostgreSQL, Redis, and monitoring:

```yaml
services:
  astromesh:
    image: ghcr.io/monaccode/astromesh:0.10.0
    ports:
      - "8000:8000"
    environment:
      - ASTROMESH_ROLE=full
      - OLLAMA_HOST=http://ollama:11434
      - DATABASE_URL=postgresql://astromesh:astromesh@postgres:5432/astromesh
      - REDIS_URL=redis://redis:6379
    depends_on:
      ollama:
        condition: service_started
      postgres:
        condition: service_started
      redis:
        condition: service_started
    volumes:
      - astromesh-data:/var/lib/astromesh
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama-models:/root/.ollama
    restart: unless-stopped

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: astromesh
      POSTGRES_USER: astromesh
      POSTGRES_PASSWORD: astromesh
    volumes:
      - postgres-data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    restart: unless-stopped

volumes:
  astromesh-data:
  ollama-models:
  postgres-data:
  redis-data:
```

## Verification

### Check all services are running

```bash
docker compose ps
```

Expected output:

```
NAME                           STATUS          PORTS
astromesh-deploy-astromesh-1    Up 2 minutes    0.0.0.0:8000->8000/tcp
astromesh-deploy-ollama-1      Up 2 minutes    11434/tcp
astromesh-deploy-postgres-1    Up 2 minutes    5432/tcp
astromesh-deploy-redis-1       Up 2 minutes    6379/tcp
```

### Health check

```bash
curl http://localhost:8000/health
```

Expected output:

```json
{
  "status": "healthy",
  "version": "0.10.0"
}
```

### List agents

```bash
curl http://localhost:8000/v1/agents
```

Expected output:

```json
{
  "agents": [
    {
      "name": "default",
      "description": "Default assistant agent",
      "model": "ollama/llama3.1:8b",
      "pattern": "react"
    }
  ]
}
```

### Run an agent

```bash
curl -X POST http://localhost:8000/v1/agents/default/run \
  -H "Content-Type: application/json" \
  -d '{"query": "Hello, what can you do?"}'
```

### View logs

```bash
# All services
docker compose logs

# Astromesh only, follow
docker compose logs -f astromesh

# Last 50 lines
docker compose logs --tail 50 astromesh
```

## Common Operations

### Stop and start

```bash
docker compose stop       # Stop without removing
docker compose start      # Start again
docker compose restart    # Restart all services
```

### Update to a new version

```bash
# Update the image tag in docker-compose.yml, then:
docker compose pull astromesh
docker compose up -d astromesh
```

### Remove everything

```bash
docker compose down           # Stop and remove containers
docker compose down -v        # Also remove volumes (deletes data)
```

## Troubleshooting

### Container exits immediately

```bash
docker compose logs astromesh
```

**Config error:**

```
ERROR: Failed to parse /etc/astromesh/runtime.yaml
```

Check your mounted config files for YAML syntax errors.

**Provider unreachable:**

```
ERROR: Cannot connect to Ollama at http://ollama:11434
```

Ensure the Ollama container is running and on the same network:

```bash
docker compose ps ollama
```

### Cannot connect from host

Verify the port mapping:

```bash
docker compose port astromesh 8000
```

Expected output:

```
0.0.0.0:8000
```

If the port is not mapped, check your `docker-compose.yml` has `ports: ["8000:8000"]`.

### Models not persisted after restart

Ensure you have a volume for Ollama models:

```yaml
volumes:
  - ollama-models:/root/.ollama
```

Without this volume, models are downloaded fresh on every container restart.

### Out of disk space

Check Docker disk usage:

```bash
docker system df
```

Clean up unused images and volumes:

```bash
docker system prune -f
docker volume prune -f
```

### Ollama on host machine

If Ollama is running directly on the host (not in Docker), use `host.docker.internal`:

```yaml
environment:
  - OLLAMA_HOST=http://host.docker.internal:11434
```

On Linux, you may need to add `extra_hosts`:

```yaml
services:
  astromesh:
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      - OLLAMA_HOST=http://host.docker.internal:11434
```
