# Changelog

All notable changes to `astromesh-adk` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `@tool` decorator now supports a single Pydantic `BaseModel` parameter (e.g. `def fn(input: MyModel)`): the auto-generated JSON schema is `MyModel.model_json_schema()` instead of degrading to `"string"`, and the wrapper accepts the model's field names as kwargs (constructing the model before calling the function) — matches how LLMs naturally call tools whose params are typed as Pydantic models. Previously a Pydantic param degraded silently and the function received a string at runtime, raising `'str' object has no attribute …` on field access (`astromesh_adk/tools.py`)

## [0.1.8] - 2026-05-22

### Added
- The ADK runner now invokes the `Callbacks` API during execution: `on_tool_result` fires after each tool call and `on_error` on a tool failure, threaded through `run_team → _run_member → run_agent → _make_tool_fn`. Callback invocations are guarded so a faulty callback cannot break a run. Previously `callbacks` was accepted by `run_agent`/`run_team` but never invoked (`astromesh_adk/runner.py`)

## [0.1.7] - 2026-05-20

### Fixed
- `resolve_provider` now passes the provider endpoint as `base_url` (and `api_key_env`) so non-default providers (notably `anthropic` → `https://api.anthropic.com/v1`) actually reach their configured endpoint instead of silently falling back to the OpenAI default (`astromesh_adk/providers.py`)

### Added
- `astromesh_adk.runner.ADKRuntime` — in-process runtime bridging ADK abstractions (`AgentWrapper`/`Agent`/`AgentTeam`) to the Astromesh core engine (orchestration patterns, `ModelRouter`, providers, tracing). Includes `_provider_and_model` model→provider mapping, `_make_model_fn` (router + fallback + system-prompt injection + `llm.complete` span), `_make_tool_fn` (`tool.call` span), and `_build_context` (`astromesh_adk/runner.py`)
- `ADKRuntime.run_agent` — executes a single agent through the core orchestration pattern (ReAct default) under an `agent.run` root span; returns a `RunResult` with cost/token/latency accounting from the trace (`astromesh_adk/runner.py`)
- `ADKRuntime.run_team` — `parallel` (concurrent fan-out, aggregated tokens/cost/spans) and `pipeline` (sequential, answer threaded stage→stage, nested `AgentTeam` supported) orchestration of multi-agent teams (`astromesh_adk/runner.py`)
- `ADKRuntime.run_team` `supervisor` and `swarm` patterns — supervisor/entry agent drives the core pattern with a delegating tool_fn that runs worker agents via `run_agent` (`astromesh_adk/runner.py`)
- `ADKRuntime.stream_agent`/`stream_class_agent` (StreamEvent step/done) and `run_class_agent` (class `Agent` lifecycle hooks on_before_run/on_after_run) (`astromesh_adk/runner.py`)

### Notes
- This release replaces the `_run_local` / `_run_parallel` / `_run_pipeline` / `_run_supervisor` MVP implementation that was version-bumped to 0.1.7 on `main` but never published to PyPI. The new implementation reuses Astromesh core orchestration patterns and the `ModelRouter` instead of duplicating that logic inside the ADK.
