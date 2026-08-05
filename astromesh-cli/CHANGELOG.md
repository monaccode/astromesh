# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-27

### Added
- `run` now surfaces the per-model consumption breakdown (`usage.by_model`, astromesh core v0.36.0): a "Por modelo" table with provider / model / role / calls / tokens in-out / cost.
- `version` now also reports the installed astromesh **core** version (via `importlib.metadata`), not just the CLI's own.

### Changed
- Bumped the astromesh core dependency pin to `>=0.36.0`.
- `run` and `ask` now read the real run-response contract (`answer` + `usage`) instead of the stale `response`/`tokens_used` field names, via a shared `_format_run_output` helper; `trace_id` is read from the nested `trace`. `ask` previously rendered an empty body against core ≥ the version that introduced `answer`.
