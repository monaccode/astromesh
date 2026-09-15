# LCA Empleado — lo que falta en astromesh

La integración `praxis_lca` (`astromesh/integrations/catalog/praxis_lca/`) está **completa para R1**:
13 acciones, publicada desde 0.52.0 y con dos arreglos posteriores —0.52.1 (el contexto de quien escribe
llega a un handler) y 0.52.2 (el «no» a la oferta de membresía se registra)—. La lista entera de la
vertical vive en `clarus-platform/docs/superpowers/fichas/lca-pendientes.md`.

## Lo que falta de este repo

- **R2a, las 14 acciones nuevas de `praxis_lca`** (`preparar_presupuesto` … `anular_operacion`), con el
  gate `exigir_paga` de la membresía y la resolución de cliente por `difflib`. Tareas, tests y mutaciones
  en `clarus-platform/docs/superpowers/plans/2026-09-15-argos-lca-r2a-plan.md` (las de astromesh).
- **Los guardrails no corren.** `AgentRuntime` construye `self._guardrails` y **nadie llama**
  `apply_input`/`apply_output` (`astromesh/runtime/engine.py`; `git grep "_guardrails\."` no encuentra un
  solo uso). Hay que cablearlos antes del patrón y antes de guardar en memoria.
- **La regla `numeros_trazables` no existe** (`astromesh/core/guardrails.py` sólo implementa
  `pii_detection` y `topic_filter`). Es el validador numérico del diseño (P4): ninguna cifra sale al canal
  si no la devolvió una tool en el turno. Hoy se suple con el prompt, y ya falló una vez: el agente de LCA
  multiplicó por su cuenta al ofrecer la membresía (dev, 2026-09-14).
- **P6, que partir una flota no cueste una cadena de LLM**: `spec.tools[].final` (ReAct termina en el
  resultado de la tool) y `spec.memory.conversational.scope` (`conv:{session}:{agente}`). Ninguno existe;
  `memory/backends/redis_conv.py` compone la clave sin segmento de agente.

## Cómo se libera cada cambio de acá

Un cambio de este repo **no hace nada** hasta que el runtime-pool de los dos Nexus corra la versión nueva:
publicar (Docker Hub **y** PyPI, que son dos caminos independientes), subir el pin en
`astromesh-nexus/deploy/components/runtime-pool/deployment.yaml` y el piso en
`clarus-platform/apps/backend/src/seeds/piso-astromesh.ts`. Runtime primero, plantilla después.
