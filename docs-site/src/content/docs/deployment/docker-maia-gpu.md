---
title: "Docker Maia + GPU"
description: "GPU-accelerated mesh deployment"
---

This guide extends the Docker Maia mesh deployment with NVIDIA GPU acceleration for Ollama inference. The inference node gets access to GPU hardware, enabling faster model execution and the ability to run larger models.

## What and Why

This deployment adds GPU passthrough to the Maia mesh so that the Ollama container runs on NVIDIA GPU hardware. This is important when you need:

- Low-latency inference for production workloads
- The ability to run large models (13B, 30B, 70B parameters) that do not fit in CPU memory
- GPU-accelerated token generation (10-50x faster than CPU)

The GPU is assigned to the Ollama container, which the inference node connects to. The rest of the mesh (gateway, workers, infrastructure) runs on CPU as before.

## Prerequisites

| Requirement | Version | Check command |
|-------------|---------|---------------|
| Docker | 24.0+ | `docker --version` |
| Docker Compose | v2.20+ | `docker compose version` |
| NVIDIA GPU | Compute Capability 7.0+ | `nvidia-smi` |
| NVIDIA Driver | 525+ | `nvidia-smi` |
| NVIDIA Container Toolkit | latest | `nvidia-ctk --version` |

### Install NVIDIA Container Toolkit

If you do not have the NVIDIA Container Toolkit installed:

```bash
# Add the NVIDIA repository
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker runtime
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Expected output:

```
INFO[0000] Config file does not exist; using defaults
INFO[0000] Successfully updated config file
INFO[0000] It is recommended that the docker daemon be restarted.
```

### Verify GPU access in Docker

```bash
nvidia-smi
```

Expected output:

```
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 535.129.03   Driver Version: 535.129.03   CUDA Version: 12.2                 |
|--------------------------------------------+------------------------+-------------------+
| GPU  Name                 Persistence-M    | Bus-Id        Disp.A  | Volatile Uncorr. ECC |
|============================+================+========================+====================|
|   0  NVIDIA RTX 4090             Off       | 00000000:01:00.0 Off  |                  Off |
+--------------------------------------------+------------------------+-------------------+
```

```bash
docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi
```

Expected output (same GPU info as above, but running inside a container):

```
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 535.129.03   Driver Version: 535.129.03   CUDA Version: 12.2                 |
|--------------------------------------------+------------------------+-------------------+
| GPU  Name                 Persistence-M    | Bus-Id        Disp.A  | Volatile Uncorr. ECC |
|============================+================+========================+====================|
|   0  NVIDIA RTX 4090             Off       | 00000000:01:00.0 Off  |                  Off |
+--------------------------------------------+------------------------+-------------------+
```

If this fails, the NVIDIA Container Toolkit is not installed correctly.

## Step-by-step Setup

### 1. Create a project directory

```bash
mkdir astromesh-gpu && cd astromesh-gpu
```

### 2. Create the Docker Compose file

Create `docker-compose.yml`:

```yaml
# Astromesh Maia Mesh — GPU Accelerated
services:
  gateway:
    image: ghcr.io/monaccode/astromesh:0.10.0
    ports:
      - "8000:8000"
    environment:
      - ASTROMESH_ROLE=gateway
      - ASTROMESH_NODE_NAME=gateway
      - ASTROMESH_MESH_ENABLED=true
      - ASTROMESH_MESH_SEEDS=gateway:8000
    networks:
      - astromesh-mesh

  worker:
    image: ghcr.io/monaccode/astromesh:0.10.0
    environment:
      - ASTROMESH_ROLE=worker
      - ASTROMESH_NODE_NAME=worker
      - ASTROMESH_MESH_ENABLED=true
      - ASTROMESH_MESH_SEEDS=gateway:8000
      - OLLAMA_HOST=http://ollama:11434
      - DATABASE_URL=postgresql://astromesh:astromesh@postgres:5432/astromesh
      - REDIS_URL=redis://redis:6379
    depends_on:
      - gateway
      - redis
      - postgres
    networks:
      - astromesh-mesh

  inference:
    image: ghcr.io/monaccode/astromesh:0.10.0
    environment:
      - ASTROMESH_ROLE=inference
      - ASTROMESH_NODE_NAME=inference
      - ASTROMESH_MESH_ENABLED=true
      - ASTROMESH_MESH_SEEDS=gateway:8000
      - OLLAMA_HOST=http://ollama:11434
    depends_on:
      - gateway
      - ollama
    networks:
      - astromesh-mesh

  # --- GPU-accelerated Ollama ---

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama-models:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    networks:
      - astromesh-mesh

  # --- Supporting infrastructure ---

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    networks:
      - astromesh-mesh

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: astromesh
      POSTGRES_USER: astromesh
      POSTGRES_PASSWORD: astromesh
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - astromesh-mesh

volumes:
  ollama-models:
  redis-data:
  postgres-data:

networks:
  astromesh-mesh:
    driver: bridge
```

The key difference from the non-GPU deployment is the `deploy.resources.reservations` block on the Ollama service, which requests GPU access from the Docker runtime.

### 3. Start the mesh

```bash
docker compose up -d
```

Expected output:

```
[+] Running 7/7
 ✔ Network astromesh-gpu_astromesh-mesh  Created
 ✔ Container astromesh-gpu-ollama-1      Started
 ✔ Container astromesh-gpu-redis-1       Started
 ✔ Container astromesh-gpu-postgres-1    Started
 ✔ Container astromesh-gpu-gateway-1     Started
 ✔ Container astromesh-gpu-worker-1      Started
 ✔ Container astromesh-gpu-inference-1   Started
```

### 4. Verify GPU inside Ollama container

```bash
docker compose exec ollama nvidia-smi
```

Expected output:

```
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 535.129.03   Driver Version: 535.129.03   CUDA Version: 12.2                 |
|--------------------------------------------+------------------------+-------------------+
| GPU  Name                 Persistence-M    | Bus-Id        Disp.A  | Volatile Uncorr. ECC |
|============================+================+========================+====================|
|   0  NVIDIA RTX 4090             Off       | 00000000:01:00.0 Off  |                  Off |
+--------------------------------------------+------------------------+-------------------+
```

### 5. Pull a model

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

### 6. Verify the mesh

```bash
curl http://localhost:8000/v1/mesh/state
```

Expected output:

```json
{
  "cluster_size": 3,
  "leader": "gateway",
  "nodes": [
    {
      "name": "gateway",
      "status": "alive",
      "role": "gateway",
      "services": ["api", "channels", "observability"],
      "address": "gateway:8000"
    },
    {
      "name": "worker",
      "status": "alive",
      "role": "worker",
      "services": ["api", "agents", "tools", "memory", "rag", "observability"],
      "address": "worker:8000"
    },
    {
      "name": "inference",
      "status": "alive",
      "role": "inference",
      "services": ["api", "inference", "observability"],
      "address": "inference:8000"
    }
  ]
}
```

### 7. Test inference

```bash
curl -X POST http://localhost:8000/v1/agents/default/run \
  -H "Content-Type: application/json" \
  -d '{"query": "Explain GPU acceleration in three sentences."}'
```

Expected output:

```json
{
  "response": "GPU acceleration uses the massively parallel architecture of graphics processing units to perform computations much faster than CPUs for workloads that can be parallelized. In the context of large language models, GPUs accelerate matrix multiplications during both training and inference, enabling real-time text generation. Modern GPUs like the NVIDIA RTX 4090 can generate tokens 10-50x faster than CPU-only inference.",
  "agent": "default",
  "model": "ollama/llama3.1:8b",
  "tokens": {
    "prompt": 18,
    "completion": 72,
    "total": 90
  }
}
```

## Configuration

### How GPU is assigned

The GPU is passed to the Ollama container via Docker's device reservation:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

- `driver: nvidia` selects the NVIDIA Container Toolkit runtime
- `count: 1` reserves one GPU
- `capabilities: [gpu]` requests GPU compute capability

The Astromesh containers (gateway, worker, inference) do not need GPU access. They communicate with Ollama over HTTP.

### Running large models

With GPU, you can run models that would be impractical on CPU:

```bash
# 13B parameter model (~7.4 GB VRAM)
docker compose exec ollama ollama pull llama3.1:13b

# 70B parameter model (~40 GB VRAM, requires high-end GPU)
docker compose exec ollama ollama pull llama3.1:70b
```

Check GPU memory usage:

```bash
docker compose exec ollama nvidia-smi
```

Expected output during inference:

```
+-----------------------------------------------------------------------------------------+
| Processes:                                                                               |
|  GPU   GI   CI        PID   Type   Process name                        GPU Memory Usage  |
|=========================================================================================|
|    0    N/A  N/A      1234    C   /usr/local/bin/ollama                     5120MiB      |
+-----------------------------------------------------------------------------------------+
```

### Multi-GPU

If you have multiple GPUs, you can assign all of them to Ollama:

```yaml
ollama:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
```

Or assign a specific number:

```yaml
devices:
  - driver: nvidia
    count: 2
    capabilities: [gpu]
```

Ollama automatically distributes model layers across available GPUs for models that exceed single-GPU memory.

### Specific GPU selection

To use a specific GPU by index (useful on multi-GPU machines):

```yaml
ollama:
  environment:
    - CUDA_VISIBLE_DEVICES=0
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
```

## Common Operations

### Monitor GPU utilization

```bash
# One-shot
docker compose exec ollama nvidia-smi

# Continuous monitoring (updates every 2 seconds)
docker compose exec ollama nvidia-smi -l 2
```

### Check model list

```bash
docker compose exec ollama ollama list
```

Expected output:

```
NAME            ID              SIZE      MODIFIED
llama3.1:8b     8eeb52dfb3bb    4.7 GB    2 hours ago
llama3.1:70b    a23f4e91c242    39 GB     30 minutes ago
```

### Scale workers

Workers do not need GPU access, so you can scale them freely:

```bash
docker compose up -d --scale worker=3
```

## Troubleshooting

### GPU not detected in container

```bash
docker compose exec ollama nvidia-smi
```

If this returns an error:

```
Failed to initialize NVML: Unknown Error
```

1. Verify the NVIDIA driver is loaded on the host:

```bash
nvidia-smi
```

2. Verify the NVIDIA Container Toolkit is installed:

```bash
nvidia-ctk --version
```

3. Restart Docker after installing the toolkit:

```bash
sudo systemctl restart docker
```

4. Recreate the container:

```bash
docker compose down ollama
docker compose up -d ollama
```

### CUDA version mismatch

```
CUDA error: no kernel image is available for execution on the device
```

Your GPU requires a newer CUDA version than the Ollama image provides. Check your driver's supported CUDA version:

```bash
nvidia-smi | grep "CUDA Version"
```

The Ollama image ships with CUDA support that matches most recent drivers. If you have an older driver, upgrade it:

```bash
sudo apt install nvidia-driver-535
sudo reboot
```

### Out of GPU memory (OOM)

```
CUDA out of memory. Tried to allocate X MiB
```

The model is too large for your GPU. Options:

1. Use a smaller model:

```bash
docker compose exec ollama ollama pull llama3.1:8b  # instead of 70b
```

2. Use a quantized variant:

```bash
docker compose exec ollama ollama pull llama3.1:8b-q4_0  # 4-bit quantization
```

3. Check what is using GPU memory:

```bash
docker compose exec ollama nvidia-smi
```

4. Stop other GPU processes or add more GPUs.

### nvidia-container-toolkit not installed

```
Error response from daemon: could not select device driver "nvidia" with capabilities: [[gpu]]
```

Install the NVIDIA Container Toolkit (see Prerequisites section) and restart Docker:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Then recreate the containers:

```bash
docker compose down
docker compose up -d
```

### Ollama not using GPU

Check Ollama logs:

```bash
docker compose logs ollama | grep -i gpu
```

Expected output when GPU is active:

```
msg="using NVIDIA GPU" gpu=0 name="NVIDIA RTX 4090" total="24564 MiB" available="23456 MiB"
```

If you see no GPU references, the NVIDIA Container Toolkit is not configured correctly. Follow the installation steps in the Prerequisites section.
