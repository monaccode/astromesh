# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN pip install --no-cache-dir uv

# Copy project files for dependency resolution
COPY pyproject.toml README.md ./
COPY astromesh-node/pyproject.toml astromesh-node/pyproject.toml
COPY astromesh-cli/pyproject.toml astromesh-cli/pyproject.toml

# Hatchling needs package directories to exist when resolving extras from local project.
RUN mkdir -p astromesh && touch astromesh/__init__.py
RUN mkdir -p astromesh-node/src/astromesh_node && touch astromesh-node/src/astromesh_node/__init__.py
RUN mkdir -p astromesh-cli/astromesh_cli && touch astromesh-cli/astromesh_cli/__init__.py

# Install third-party dependencies in a cache-friendly layer.
# config/ must exist at this point because pyproject.toml force-includes it
# into the wheel under astromesh/_bundled/config; without it, hatchling aborts.
ARG ASTROMESH_EXTRAS="redis,postgres,sqlite,qdrant,observability,mcp,mesh"
COPY config/ config/
RUN uv pip install --system ".[${ASTROMESH_EXTRAS}]"
RUN uv pip install --system ./astromesh-node ./astromesh-cli || true

# Copy source after dependencies so code changes do not invalidate dependency layer.
COPY astromesh/ astromesh/
COPY astromesh-node/src/astromesh_node/ astromesh-node/src/astromesh_node/
COPY astromesh-cli/astromesh_cli/ astromesh-cli/astromesh_cli/

# Install local projects without re-resolving dependencies.
RUN uv pip install --system --no-deps .
RUN uv pip install --system --no-deps ./astromesh-node ./astromesh-cli

# Stage 2: Runtime image
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Astromesh" \
      org.opencontainers.image.description="Astromesh Agent Runtime Platform" \
      org.opencontainers.image.source="https://github.com/monaccode/astromesh"

WORKDIR /opt/astromesh

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/astromeshd /usr/local/bin/astromeshctl /usr/local/bin/

# Copy application code
COPY astromesh/ astromesh/
COPY astromesh-node/src/astromesh_node/ astromesh_node/
COPY astromesh-cli/astromesh_cli/ astromesh_cli/

# Default config (overridden via volume mount)
COPY config/ /etc/astromesh/

# Smart entrypoint: env vars → config generation
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Create runtime directories
RUN mkdir -p /var/lib/astromesh/data /var/lib/astromesh/models \
             /var/lib/astromesh/memory /var/log/astromesh/audit

# Default environment variables
ENV ASTROMESH_ROLE=full \
    ASTROMESH_MESH_ENABLED=false \
    ASTROMESH_NODE_NAME="" \
    ASTROMESH_SEEDS="" \
    ASTROMESH_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/v1/health').raise_for_status()"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["--config", "/etc/astromesh"]
