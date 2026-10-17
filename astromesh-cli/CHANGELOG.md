# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- La plantilla de `new agent` usaba `orchestration.timeout: 30`; con core 0.71 eso corta la corrida a los 30 s. Ahora emite `timeout_seconds: 120`.

## [0.4.0] - 2026-10-16

### Added
- `astromeshctl eval <config_dir> [archivos...] [--out reporte.json]`: corre los `kind: Eval` con
  el runner del core (`astromesh.evals`, el mismo de `astromesh-eval`). Exit 0 si todos cumplen,
  1 si alguno queda bajo umbral, 2 por error de carga (un eval inválido no corre ningún caso).
- `run` muestra un panel **BLOCKED by guardrail** con dirección, regla y motivo cuando el core
  0.70 bloquea la corrida (que vuelve HTTP 200 con el rechazo como `answer`), y una tabla con las
  `propuestas` de las tools `mode: propose`. La tabla por modelo suma la columna `Cached`
  (`tokens_cached`).
- `new agent --context-window N`; la plantilla trae `guardrails` válidos para el core 0.70
  (`pii_detection` en entrada y salida, `max_length`, `cost_limit` 4000), `context_window`
  (comentado si no se pasa) y un `knowledge.bundle` comentado. Un test la carga con
  `AgentRuntime` sin warnings de guardrails.

### Changed
- Piso del core `astromesh>=0.70.0`.

## [0.3.1] - 2026-09-27

### Changed
- Bumped the `astromesh` core dependency floor to `>=0.59.0` (`pyproject.toml`). No CLI code changes.

## [0.2.1] - 2026-08-10

### Changed
- Bumped the `astromesh` core dependency floor to `>=0.40.0` (`pyproject.toml`).

## [0.2.0] - 2026-07-27

### Added
- `run` now surfaces the per-model consumption breakdown (`usage.by_model`, astromesh core v0.36.0): a "Por modelo" table with provider / model / role / calls / tokens in-out / cost.
- `version` now also reports the installed astromesh **core** version (via `importlib.metadata`), not just the CLI's own.

### Changed
- Bumped the astromesh core dependency pin to `>=0.36.0`.
- `run` and `ask` now read the real run-response contract (`answer` + `usage`) instead of the stale `response`/`tokens_used` field names, via a shared `_format_run_output` helper; `trace_id` is read from the nested `trace`. `ask` previously rendered an empty body against core ≥ the version that introduced `answer`.
