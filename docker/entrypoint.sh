#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="/etc/astromesh"
RUNTIME_YAML="$CONFIG_DIR/runtime.yaml"

# If auto-config is disabled, use mounted config directly
if [ "${ASTROMESH_AUTO_CONFIG:-true}" != "true" ]; then
    if [ ! -f "$RUNTIME_YAML" ]; then
        echo "[entrypoint] ERROR: ASTROMESH_AUTO_CONFIG=false but no config found at $RUNTIME_YAML"
        echo "[entrypoint] Mount your config: -v ./runtime.yaml:/etc/astromesh/runtime.yaml"
        exit 1
    fi
    echo "[entrypoint] Using mounted config at $RUNTIME_YAML"
    exec astromeshd "$@"
fi

ROLE="${ASTROMESH_ROLE:-full}"
MESH="${ASTROMESH_MESH_ENABLED:-false}"

# Select profile based on role and mesh mode
if [ "$MESH" = "true" ]; then
    PROFILE="$CONFIG_DIR/profiles/mesh-${ROLE}.yaml"
else
    PROFILE="$CONFIG_DIR/profiles/${ROLE}.yaml"
fi

# Validate profile exists
if [ ! -f "$PROFILE" ]; then
    echo "[entrypoint] ERROR: Profile not found: $PROFILE"
    echo "[entrypoint] Available profiles:"
    ls -1 "$CONFIG_DIR/profiles/" 2>/dev/null || echo "  (none)"
    exit 1
fi

# Generate runtime.yaml from profile with env var overrides
python3 -c "
import yaml, os, socket

with open('$PROFILE') as f:
    profile = yaml.safe_load(f)

# Patch mesh settings from env
mesh = profile.get('spec', {}).get('mesh')
if mesh:
    mesh['node_name'] = os.environ.get('ASTROMESH_NODE_NAME') or socket.gethostname()
    seeds_raw = os.environ.get('ASTROMESH_SEEDS', '')
    if seeds_raw.strip():
        mesh['seeds'] = [s.strip() for s in seeds_raw.split(',') if s.strip()]

# Patch API port
port = int(os.environ.get('ASTROMESH_PORT', '8000'))
profile.setdefault('spec', {}).setdefault('api', {})['port'] = port

with open('$RUNTIME_YAML', 'w') as f:
    yaml.dump(profile, f, default_flow_style=False, sort_keys=False)
"

echo "[entrypoint] Generated $RUNTIME_YAML (role=$ROLE, mesh=$MESH)"
exec astromeshd "$@"
