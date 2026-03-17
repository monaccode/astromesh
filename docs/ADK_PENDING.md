# Astromesh ADK — Pendientes de Implementacion

## Estado Actual

El paquete `astromesh-adk` esta implementado con todas las interfaces publicas funcionando (89 tests passing). El `ADKRuntime` es un stub que define la API pero lanza `NotImplementedError` en los metodos de ejecucion.

---

## Task 13: ADKRuntime — Implementacion Completa

**Archivo:** `astromesh-adk/astromesh_adk/runner.py`
**Plan completo:** `docs/superpowers/plans/2026-03-17-astromesh-adk.md` (Task 13)

### Metodos pendientes

| Metodo | Descripcion |
|--------|-------------|
| `run_agent()` | Ejecutar agente decorator-based localmente via Astromesh core |
| `run_class_agent()` | Ejecutar agente class-based con lifecycle hooks |
| `stream_agent()` | Streaming con token chunking para decorator agents |
| `stream_class_agent()` | Streaming para class-based agents |
| `run_team()` | Ejecutar AgentTeam traduciendo a OrchestrationPattern |
| `_run_local()` | Pipeline completo: provider -> router -> memory -> guardrails -> orchestration -> persist |
| `_run_remote()` | Delegacion a Astromesh remoto via HTTP |
| `_build_tools_registry()` | Traducir ADK tools a Astromesh ToolRegistry |
| `_build_pattern()` | Resolver nombre de patron a instancia de OrchestrationPattern |

### Pipeline de ejecucion local (`_run_local`)

```
1. parse_model_string() -> resolve_provider() -> ModelRouter
2. _build_tools_registry() -> ToolRegistry con tools del agente
3. _build_pattern() -> OrchestrationPattern (ReAct, PlanAndExecute, etc.)
4. MemoryManager(agent_id, config) -> build_context()
5. GuardrailsEngine(config) -> apply_input()
6. PromptEngine().render(system_prompt, {memory, context})
7. model_fn = closure sobre router.route()
8. tool_fn = closure sobre registry.execute() + callbacks
9. Handler check: si handler retorna None -> orchestration pattern
10. pattern.execute(query, context, model_fn, tool_fn, tools, max_iterations)
11. guardrails.apply_output()
12. memory_mgr.persist_turn() (user + assistant)
13. RunResult.from_runtime(result)
```

### Imports de Astromesh necesarios

```python
from astromesh.core.tools import ToolRegistry, ToolDefinition, ToolType
from astromesh.core.model_router import ModelRouter
from astromesh.core.memory import MemoryManager, ConversationTurn
from astromesh.core.guardrails import GuardrailsEngine
from astromesh.core.prompt_engine import PromptEngine
from astromesh.orchestration.patterns import (
    ReActPattern, PlanAndExecutePattern, ParallelFanOutPattern, PipelinePattern
)
from astromesh.orchestration.supervisor import SupervisorPattern
from astromesh.orchestration.swarm import SwarmPattern
from astromesh.observability.tracing import TracingContext, SpanStatus
```

### Mapping de patrones

```python
PATTERN_MAP = {
    "react": ReActPattern,
    "plan_and_execute": PlanAndExecutePattern,
    "parallel_fan_out": ParallelFanOutPattern,
    "parallel": ParallelFanOutPattern,  # shorthand
    "pipeline": PipelinePattern,
    "supervisor": SupervisorPattern,
    "swarm": SwarmPattern,
}
```

### Prerequisitos para implementar

1. **Tests de integracion con providers mockeados** — usar `respx` para mockear HTTP calls de providers
2. **Verificar constructores** — los constructores de ModelRouter, MemoryManager, etc. pueden haber cambiado
3. **MCP discovery** — `MCPToolSet.discover()` necesita ser invocado en la primera ejecucion
4. **Lifecycle cleanup** — `ADKRuntime.shutdown()` debe cerrar MCP clients y Tool.cleanup()

---

## Mejoras Futuras (Post v1)

### Documentacion docs-site pendiente

Paginas MDX por crear en `docs-site/src/content/docs/adk/`:

| Pagina | Slug | Contenido |
|--------|------|-----------|
| Defining Agents | `adk/defining-agents` | @agent decorator, Agent class, lifecycle hooks, system prompt |
| Creating Tools | `adk/creating-tools` | @tool decorator, Tool class, MCP integration, schema generation |
| Multi-Agent Teams | `adk/multi-agent` | AgentTeam, supervisor/swarm/pipeline/parallel patterns |
| Remote Execution | `adk/remote-execution` | connect(), disconnect(), remote(), bind(), concurrency |
| CLI Reference | `adk/cli-reference` | run, chat, list, check, dev commands detallados |
| Provider Config | `adk/providers` | String shorthands, model_config, fallback, routing |
| Memory & State | `adk/memory` | Shorthand strings, full dict config, backends |
| Observability | `adk/observability` | RunResult fields, Callbacks, structured logging |
| API Reference | `adk/api-reference` | Referencia completa de todas las clases y funciones |
| Examples & Cookbook | `adk/examples` | Patrones comunes, recetas |
| Migration from YAML | `adk/migration-from-yaml` | Guia para migrar de agent YAML a ADK Python |

### Nuevos endpoints Astromesh (para modo remoto)

| Endpoint | Metodo | Proposito |
|----------|--------|-----------|
| `/v1/agents` | `POST` | Registrar agente desde ADK |
| `/v1/agents/{name}` | `PUT` | Actualizar definicion de agente |
| `/v1/agents/{name}` | `DELETE` | Eliminar agente |
| `/v1/auth/token` | `POST` | Validacion de API key |

### AnthropicProvider nativo

v1 usa `OpenAICompatProvider` para Anthropic. v1.1 debe implementar un `AnthropicProvider` dedicado con soporte nativo para system prompts y tool use format de Anthropic.

### Streaming real

v1 implementa streaming como chunked replay del resultado completo. v1.1 debe implementar token streaming real usando `provider.stream()` intercalado con la orquestacion.

### Ejemplos adicionales

- `examples/remote_execution.py` — connect/disconnect/remote patterns
- `examples/callbacks_example.py` — custom callbacks para logging/metrics
