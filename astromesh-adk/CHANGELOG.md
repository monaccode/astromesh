# Changelog

## [0.1.7] - 2026-04-26

### Added
- `ADKRuntime._run_local()` — local in-process execution loop with multi-provider support (anthropic + openai)
- `ADKRuntime._stream_local()` — streaming variant emitting `StreamEvent` per step
- `ADKRuntime._run_pipeline()` — sequential pipeline with output[N] → input[N+1] context propagation
- `ADKRuntime._run_parallel()` — parallel fan-out using `asyncio.TaskGroup`, aggregated results in `previous_outputs`
- `ADKRuntime._run_supervisor()` — supervisor loop with `delegate_to` tool calls until `final_answer`
- Internal helper `astromesh_adk._internal.llm_dispatch` for provider calls with retry + fallback chain
