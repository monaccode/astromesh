# Astromesh ADK — Estado y Pendientes

Este documento describe de forma clara que partes del ADK ya estan listas, que componentes todavia son stub, y cual es el orden recomendado para completar la implementacion.

---

## Resumen ejecutivo

- El paquete `astromesh-adk` expone su API publica principal y tiene cobertura de pruebas base.
- El cuello de botella actual es `ADKRuntime` en `astromesh-adk/astromesh_adk/runner.py`.
- La prioridad es implementar ejecucion local/remota, streaming y traduccion completa de tools/patrones.

---

## Estado actual

### Lo que ya funciona

- Decoradores y estructuras publicas del ADK
- Flujos de uso basicos y CLI
- Suite de pruebas existente (89 tests en verde, segun estado reportado)

### Lo que aun es parcial

`ADKRuntime` mantiene la interfaz esperada, pero varios metodos de ejecucion todavia lanzan `NotImplementedError`.

---

## Bloque critico: Task 13 (ADKRuntime)

**Archivo objetivo:** `astromesh-adk/astromesh_adk/runner.py`  
**Plan fuente:** `docs/superpowers/plans/2026-03-17-astromesh-adk.md` (Task 13)

### Metodos pendientes y objetivo funcional

| Metodo | Objetivo |
|--------|----------|
| `run_agent()` | Ejecutar agentes declarados con decoradores en runtime local |
| `run_class_agent()` | Ejecutar agentes class-based con lifecycle hooks |
| `stream_agent()` | Streaming para agentes decorator-based |
| `stream_class_agent()` | Streaming para agentes class-based |
| `run_team()` | Ejecutar `AgentTeam` traduciendo configuracion a patron de orquestacion |
| `_run_local()` | Pipeline completo dentro de Astromesh core |
| `_run_remote()` | Delegacion a runtime Astromesh remoto via HTTP |
| `_build_tools_registry()` | Adaptar tools ADK a `ToolRegistry` |
| `_build_pattern()` | Resolver string de patron a `OrchestrationPattern` concreto |

---

## Flujo esperado de ejecucion local (`_run_local`)

```text
1. Resolver modelo/proveedor -> ModelRouter
2. Construir ToolRegistry desde tools ADK
3. Resolver patron de orquestacion (react, plan_and_execute, etc.)
4. Construir contexto de memoria
5. Aplicar guardrails de entrada
6. Renderizar prompt final (system + context)
7. Ejecutar loop de razonamiento/orquestacion (modelo + tools)
8. Aplicar guardrails de salida
9. Persistir turno en memoria (user/assistant)
10. Normalizar salida a RunResult
```

Este orden es clave para mantener paridad entre ejecucion ADK y runtime YAML de Astromesh.

---

## Dependencias internas de Astromesh necesarias

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

---

## Mapping de patrones (referencia)

```python
PATTERN_MAP = {
    "react": ReActPattern,
    "plan_and_execute": PlanAndExecutePattern,
    "parallel_fan_out": ParallelFanOutPattern,
    "parallel": ParallelFanOutPattern,
    "pipeline": PipelinePattern,
    "supervisor": SupervisorPattern,
    "swarm": SwarmPattern,
}
```

---

## Riesgos y prerequisitos antes de cerrar Task 13

1. **Tests de integracion con providers mockeados**  
   Usar `respx` para simular respuestas HTTP de providers y cubrir errores/retries.
2. **Verificacion de firmas actuales**  
   Confirmar constructores y contratos de `ModelRouter`, `MemoryManager`, `GuardrailsEngine`.
3. **Discovery MCP en primer uso**  
   Asegurar llamada inicial a `MCPToolSet.discover()` cuando aplique.
4. **Limpieza de recursos**  
   `ADKRuntime.shutdown()` debe cerrar clientes MCP y ejecutar `Tool.cleanup()`.

---

## Mejoras post-v1 (no bloqueantes para release inicial)

### Documentacion ADK para docs-site

Paginas MDX propuestas en `docs-site/src/content/docs/adk/`:

| Pagina | Slug | Alcance |
|--------|------|---------|
| Defining Agents | `adk/defining-agents` | Decorator API, clases, lifecycle hooks, system prompt |
| Creating Tools | `adk/creating-tools` | `@tool`, clases tool, MCP, schemas |
| Multi-Agent Teams | `adk/multi-agent` | Team config y patrones (supervisor/swarm/pipeline/parallel) |
| Remote Execution | `adk/remote-execution` | `connect()`, `disconnect()`, `remote()`, `bind()` |
| CLI Reference | `adk/cli-reference` | `run`, `chat`, `dev`, `list`, `check` |
| Provider Config | `adk/providers` | Shorthands de modelo, routing, fallback |
| Memory & State | `adk/memory` | Config de memoria corta/larga y backends |
| Observability | `adk/observability` | `RunResult`, callbacks, trazas y logs |
| API Reference | `adk/api-reference` | Referencia formal de clases/funciones |
| Examples & Cookbook | `adk/examples` | Recetas listas para copiar |
| Migration from YAML | `adk/migration-from-yaml` | Guia de migracion desde agentes YAML |

### Endpoints remotos recomendados

| Endpoint | Metodo | Proposito |
|----------|--------|-----------|
| `/v1/agents` | `POST` | Registrar agentes desde ADK |
| `/v1/agents/{name}` | `PUT` | Actualizar definiciones |
| `/v1/agents/{name}` | `DELETE` | Eliminar agentes |
| `/v1/auth/token` | `POST` | Validar API key/token |

### Mejoras tecnicas deseables

- **Provider Anthropic nativo:** reemplazar compat layer por implementacion dedicada.
- **Streaming real por token:** usar `provider.stream()` en vez de replay chunked.
- **Ejemplos extra:** `examples/remote_execution.py`, `examples/callbacks_example.py`.
