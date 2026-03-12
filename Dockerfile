# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml .
COPY README.md .

# Keep runtime image lean by default; override with --build-arg ASTROMESH_EXTRAS=all if needed.
ARG ASTROMESH_EXTRAS="redis,postgres,sqlite,qdrant,observability,mcp,cli,daemon,mesh"

# Hatchling needs package directories to exist when resolving extras from local project.
# Create a minimal skeleton so dependency layer remains cacheable before copying full source.
RUN mkdir -p astromesh daemon cli && \
    touch astromesh/__init__.py daemon/__init__.py cli/__init__.py

# Install third-party dependencies in a cache-friendly layer.
RUN uv pip install --system ".[${ASTROMESH_EXTRAS}]"

# Copy source after dependencies so code changes do not invalidate dependency layer.
COPY astromesh/ astromesh/
COPY daemon/ daemon/
COPY cli/ cli/

# Install local project without re-resolving dependencies.
RUN uv pip install --system --no-deps .

# Stage 2: Runtime image
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Astromesh OS" \
      org.opencontainers.image.description="Astromesh Agent Runtime Platform" \
      org.opencontainers.image.source="https://github.com/monaccode/astromesh"

WORKDIR /opt/astromesh

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/astromeshd /usr/local/bin/astromeshctl /usr/local/bin/

# Copy application code
COPY astromesh/ astromesh/
COPY daemon/ daemon/
COPY cli/ cli/

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
