# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml .
COPY astromesh/ astromesh/
COPY daemon/ daemon/
COPY cli/ cli/

# Install all dependencies
RUN uv pip install --system ".[all]"

# Stage 2: Runtime image
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Astromesh OS" \
      org.opencontainers.image.description="Astromesh Agent Runtime Platform" \
      org.opencontainers.image.source="https://github.com/monaccode/astromech-platform"

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
