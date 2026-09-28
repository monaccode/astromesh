# Changelog

All notable changes to `astromesh-node` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.5] - 2026-09-28

### Changed
- Bumped the `astromesh` core dependency floor to `>=0.60.0` (`AgentRuntime.reload()`).

### Added
- **SIGHUP / `systemctl reload` recarga los agentes** vía `runtime.reload()` (core ≥ 0.60.0), entre `RELOADING=1` y `READY=1`; un fallo se loguea y el daemon sigue. `runtime.yaml` requiere reinicio y se avisa si cambió.

## [0.1.4] - 2026-09-28

### Fixed
- **astromeshd ya no muere cada 30 segundos bajo systemd.** La unidad declara
  `WatchdogSec=30` y el daemon mandaba `READY=1` pero nunca `WATCHDOG=1`, así que systemd
  lo mataba y `Restart=on-failure` lo levantaba de nuevo, en loop. astromesh-os lo esquivaba
  con un drop-in `WatchdogSec=0`. Ahora `SystemdManager` hace ping a la mitad de
  `WATCHDOG_USEC` desde el event loop (si el loop se cuelga, el ping para y systemd lo
  reinicia, que es para lo que está el watchdog), respeta `WATCHDOG_PID` y deja de hacer
  ping en `notify_stopping` (`astromesh-node/src/astromesh_node/platform/systemd.py`).

## [0.1.3] - 2026-09-27

### Changed
- Bumped the `astromesh` core dependency floor to `>=0.59.0` and `astromesh-cli` to `>=0.3.1` (`pyproject.toml`).

## [0.1.2] - 2026-08-10

### Changed
- Bumped the `astromesh` core dependency floor to `>=0.40.0` (`pyproject.toml`).
- Bumped the `astromesh-cli` dependency floor to `>=0.2.1` (`pyproject.toml`).
