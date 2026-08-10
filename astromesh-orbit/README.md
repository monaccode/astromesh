# Astromesh Orbit

<p align="center">
  <a href="https://monaccode.github.io/astromesh/#ecosystem"><img src="https://img.shields.io/badge/astromesh-ship-fb923c?labelColor=161b22" alt="Astromesh · Ship"></a>
  <a href="https://github.com/monaccode/astromesh/actions/workflows/ci.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://github.com/monaccode/astromesh/actions/workflows/release-orbit.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/release-orbit.yml/badge.svg" alt="Orbit Publish"></a>
  <a href="https://pypi.org/project/astromesh-orbit/"><img src="https://img.shields.io/pypi/v/astromesh-orbit?label=Orbit%20PyPI" alt="Orbit PyPI"></a>
  <a href="https://test.pypi.org/project/astromesh-orbit/"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Ftest.pypi.org%2Fpypi%2Fastromesh-orbit%2Fjson&query=%24.info.version&label=Orbit%20TestPyPI" alt="Orbit TestPyPI"></a>
  <a href="https://github.com/monaccode/astromesh/blob/develop/LICENSE"><img src="https://img.shields.io/github/license/monaccode/astromesh" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python 3.12+"></a>
</p>

Cloud-native deployment for Astromesh — provision infrastructure on any cloud.

Today Orbit supports **GCP** (Cloud Run, Cloud SQL, Redis, Secret Manager, Cloud Storage, Artifact Registry, Cloud Monitoring, Cloud Trace). AWS and Azure are on the roadmap.

## Install

```bash
pip install astromesh-orbit[gcp]
```

## Quick start

```bash
# Generate orbit.yaml through an interactive wizard
astromeshctl orbit init --provider gcp

# Preview infrastructure changes
astromeshctl orbit plan

# Deploy
astromeshctl orbit apply

# Inspect and operate
astromeshctl orbit status
astromeshctl orbit logs
astromeshctl orbit upgrade

# Tear down
astromeshctl orbit destroy
```

## Eject to Terraform

Orbit renders Terraform templates under `.orbit/generated/`. You can inspect, edit, and eject to raw Terraform at any time:

```bash
astromeshctl orbit eject
```

## Documentation

- [Orbit Overview](../docs/ORBIT_OVERVIEW.md)
- [Orbit Quick Start](../docs/ORBIT_QUICKSTART.md)
- [Orbit Configuration](../docs/ORBIT_CONFIGURATION.md)
- [Astromesh Docs](https://monaccode.github.io/astromesh/)

## License

Apache-2.0
