# Changelog

All notable changes to `astromesh-node` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Actualizar el paquete ya no deja el servicio parado ni deshabilitado.** `preremove.sh` hacía
  stop + disable siempre, también en un upgrade: en rpm el `%preun` del paquete viejo corre
  después del `%post` del nuevo y dejaba el nodo parado y deshabilitado; en deb `prerm upgrade`
  lo paraba y nadie lo volvía a arrancar. Ahora sólo lo hace en una desinstalación real, y
  `postinstall.sh` distingue instalación nueva (`enable`, sin arrancar) de upgrade
  (`try-restart`, respetando si el admin lo había deshabilitado).
- **`astromeshctl init` encuentra sus perfiles en una instalación empaquetada.** Los buscaba
  relativos a su propio archivo, lo que sólo existía en un checkout: instalado apuntaba adentro
  del venv, escribía un `runtime.yaml` vacío y seguía. Ahora los lee del config que el core ya
  empaqueta (`astromesh/_bundled/config`, o `config/` en editable) y, si falta el perfil, corta
  con código 1. Como admin usa el config dir de cada plataforma (en macOS y Windows no es
  `/etc/astromesh`). La copia duplicada `astromesh-node/config/profiles` se va; el `.deb`/`.rpm`
  toma los perfiles de `config/profiles`.

## [0.1.7] - 2026-09-28

### Fixed
- **`--foreground` ya no muere con SIGHUP.** `ForegroundManager` guardaba el handler de recarga
  pero no registraba la señal, y la acción por defecto de SIGHUP es terminar el proceso: en
  Docker o en dev, `kill -HUP` mataba el daemon en vez de recargar los agentes
  (`astromesh-node/src/astromesh_node/platform/foreground.py`).

## [0.1.6] - 2026-09-28

### Fixed
- **`validate` y `config validate` salen con `1` cuando encuentran errores.** Imprimían los
  errores y salían con `0`, así que no servían de gate en CI; `config validate` salía con `0`
  incluso sin directorio de config (`astromesh-node/src/astromesh_node/cli/commands/`).

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
