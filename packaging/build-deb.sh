#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Extract version from pyproject.toml
VERSION=$(grep '^version = ' pyproject.toml | head -1 | sed 's/version = "\(.*\)"/\1/')
export VERSION

echo "==> Building astromesh ${VERSION} .deb package"

# Create staging area
rm -rf staging
mkdir -p staging

# Create venv with project installed
echo "==> Creating virtual environment..."
python3.12 -m venv staging/venv
staging/venv/bin/pip install --upgrade pip --quiet
staging/venv/bin/pip install ".[cli,daemon]" --quiet

# Strip unnecessary files to reduce package size
echo "==> Stripping __pycache__ and .dist-info test dirs..."
find staging/venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find staging/venv -type d -name "tests" -path "*/site-packages/*/tests" -exec rm -rf {} + 2>/dev/null || true
find staging/venv -type d -name "test" -path "*/site-packages/*/test" -exec rm -rf {} + 2>/dev/null || true

# Build .deb with nfpm
echo "==> Running nfpm..."
mkdir -p dist
nfpm package --packager deb --target dist/

DEB_FILE="dist/astromesh_${VERSION}_amd64.deb"
if [ -f "$DEB_FILE" ]; then
    echo "==> Success: $DEB_FILE"
    dpkg-deb --info "$DEB_FILE" 2>/dev/null || true
else
    echo "==> ERROR: Expected $DEB_FILE not found"
    ls -la dist/
    exit 1
fi
