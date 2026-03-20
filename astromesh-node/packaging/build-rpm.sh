#!/usr/bin/env bash
set -euo pipefail

VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
echo "Building astromesh-node ${VERSION} RPM..."

# Reuse the same staging as deb (or create if not exists)
if [ ! -d "staging/venv" ]; then
    python3 -m venv staging/venv
    staging/venv/bin/pip install --quiet ../  .[systemd]
    find staging/venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find staging/venv -type d -name tests -exec rm -rf {} + 2>/dev/null || true
fi

mkdir -p dist
VERSION="${VERSION}" nfpm package --config packaging/nfpm.yaml --packager rpm --target dist/
echo "Built dist/astromesh-node-${VERSION}.x86_64.rpm"
