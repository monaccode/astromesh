#!/bin/bash
# Builds the runtime the .deb and .rpm ship, AT ITS FINAL PATH: a standalone CPython in
# /opt/astromesh/python and the venv in /opt/astromesh/venv. Both must be built where they
# will live — a venv is not relocatable: its shebangs and pyvenv.cfg carry absolute paths.
# Until node 0.1.7 the venv was built in a CI staging dir with the runner's toolcache
# Python, so every published .deb/.rpm pointed at /home/runner/... and
# /opt/hostedtoolcache/... and failed with "bad interpreter" on any real machine.
#
# Needs a writable /opt/astromesh (root in a container, or a pre-created dir in CI).
# Run from astromesh-node/.
set -euo pipefail

PREFIX="${ASTROMESH_PREFIX:-/opt/astromesh}"
# python-build-standalone: relocatable CPython, glibc >= 2.17 (RHEL 8+, Debian 11+, Ubuntu 20.04+).
PBS_RELEASE="20260924"
PY_VERSION="3.12.14"
# `_stripped`: no debug symbols — libpython alone drops from 113 MB.
PY_ASSET="cpython-${PY_VERSION}+${PBS_RELEASE}-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PY_SHA256="269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41"
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE}/${PY_ASSET}"

echo "==> Standalone CPython ${PY_VERSION} into ${PREFIX}/python"
rm -rf "${PREFIX}/python" "${PREFIX}/venv"
mkdir -p "${PREFIX}"
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
curl -fsSL "${PY_URL}" -o "${tmp}/python.tar.gz"
echo "${PY_SHA256}  ${tmp}/python.tar.gz" | sha256sum -c -
tar -xzf "${tmp}/python.tar.gz" -C "${PREFIX}"   # unpacks to python/

echo "==> venv at ${PREFIX}/venv"
"${PREFIX}/python/bin/python3" -m venv "${PREFIX}/venv"
"${PREFIX}/venv/bin/pip" install --upgrade pip --quiet
# The core `observability` extra ships the OpenTelemetry SDK + OTLP exporter the runtime's
# trace export needs (Fase 4.3); `systemd` brings sdnotify for Type=notify and the watchdog.
"${PREFIX}/venv/bin/pip" install "../[observability]" ".[systemd]" --quiet

echo "==> Stripping __pycache__ and test dirs"
find "${PREFIX}/venv" "${PREFIX}/python" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${PREFIX}/venv" -type d \( -name tests -o -name test \) -path "*/site-packages/*/test*" \
    -exec rm -rf {} + 2>/dev/null || true
find "${PREFIX}/python/lib" -maxdepth 2 -type d -name test -exec rm -rf {} + 2>/dev/null || true
# A headless daemon has no use for Tk: drop tkinter/idle and the Tcl/Tk libraries.
rm -rf "${PREFIX}"/python/lib/python3.*/{tkinter,idlelib,turtledemo} \
    "${PREFIX}"/python/lib/{tcl,tk,itcl,thread}* "${PREFIX}"/python/lib/lib{tcl,tk}*

# Fail the build, not the install: every python script must point at the final venv.
bad=0
for f in "${PREFIX}/venv/bin/"*; do
    [ -f "${f}" ] && [ ! -L "${f}" ] || continue
    first=$(head -n1 "${f}" 2>/dev/null || true)
    case "${first}" in
        "#!${PREFIX}/venv/bin/python"*) ;;
        "#!"*python*) echo "==> ERROR: ${f} has shebang ${first}"; bad=1 ;;
    esac
done
[ "${bad}" = "0" ] || exit 1
"${PREFIX}/venv/bin/python" -c "import astromesh.api.main, astromesh_node; print('==> venv OK', astromesh_node.__version__)"
