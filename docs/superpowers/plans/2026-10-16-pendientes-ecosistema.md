# Pendientes del ecosistema tras la ronda de paridad con core 0.70.0

> Estado al 2026-10-16. La ronda dejó publicados: ADK 0.5.0, CLI 0.4.0 (PyPI), Forge 0.27.0,
> Cortex v0.26.0, Leia v0.8.0, Nexus 0.26.12 (dev + mvp) y docs-site. Lo de abajo quedó
> fuera **a propósito** o salió a la luz durante la ronda. Ordenado por prioridad; cada ítem
> dice dónde está, qué hay que hacer y cómo se verifica. Los marcados **(feature)** van por
> el pipeline completo (brainstorm → spec → plan → SDD); el resto son arreglos acotados.

## P1 — Comportamiento que hoy engaña al usuario

### 1. Secciones del manifiesto que el core acepta pero no aplica **(feature, una por sección)**
- `permissions.allowed_actions` / `denied_actions`: no-op en el engine.
- `memory.semantic` / `memory.episodic`: documentadas, nunca se construyen desde el manifiesto.
- `swarm`: el engine arma `SwarmPattern` sin agentes, el handoff no funciona.
- `orchestration.timeout_seconds`: no se lee.
- Hoy docs-site, Cortex y Forge las marcan como inertes. Decidir por cada una: implementarla
  o rechazarla al cargar (`AgentConfigError` / warning), en vez de aceptarla en silencio.
- Verificación: test en `tests/` que cargue un manifiesto con la sección y compruebe que se
  aplica (o que se rechaza); después, quitar las advertencias de docs-site, Cortex y Forge.

### 2. ADK: compuerta de confirmación y `mode: propose` en corridas locales **(feature)**
- Hoy solo existen en corridas remotas. En local una tool de escritura corre sin confirmar.
- Requiere que `ADKRuntime` use el `ToolRegistry` del core (o un adaptador) en lugar de su
  propio `tool_fn`: es rediseño del runner (`astromesh-adk/astromesh_adk/runner.py`).
- De paso: streaming local más allá del evento `done`, y un adaptador para correr evals
  (`kind: Eval`) contra agentes del ADK.
- Verificación: tests en `astromesh-adk/tests/` con una tool `confirm: true` y un agente en
  `mode: propose`; `RunResult.propuestas` poblado en local.

### 3. Nexus: persistir `blocked` en la invocación
- 0.26.12 reenvía `blocked`/`guardrail` en `/run` y `/run/stream`, pero no lo guarda:
  `GET …/invocations/:id`, `/logs` y las métricas no distinguen un rechazo.
- Migración de esquema (columna `blocked bool` + `guardrail jsonb` o dentro de metadata),
  handler que la escriba y lectura en invocations/logs.
- Verificación: `go test ./...` con una invocación bloqueada que se lee después; Leia
  `/leia logs` puede mostrar el rechazo.

## P2 — Huecos acotados

### 4. `astromeshctl validate` (node) no reconoce `*.eval.yaml`
- `astromesh-node/src/astromesh_node/cli/commands/validate.py`: agregar
  `".eval.yaml": "Eval"` a `KIND_EXPECTATIONS` (y validar contra `astromesh.evals.formato`).
- Implica release de node (paquetes con CPython embebido; ver memoria de packaging).
  Empujar el tag `cli-v*` antes que `node-v*` si cambia el piso del CLI.

### 5. Guardrails: menores diferidos de 0.70.0
- En cadenas (`chain`) solo aflora el bloqueo del agente de entrada.
- Si `_persistir_turno` falla dentro del handler de bloqueo, no se loguea.
- Spans multimodales con el mismo nombre.
- `casefold` en Python vs lowercase en el camino nativo de Rust: comparar resultados.
- El camino nativo (`_native`) no se compila en CI, así que no está verificado: agregar un
  job que haga `maturin develop` y corra los tests de guardrails con y sin
  `ASTROMESH_FORCE_PYTHON=1`.

### 6. Nexus: el pool no monta bundles OKF
- `spec.knowledge.bundle` solo funciona en nodos standalone; el deployment del pool monta
  únicamente `runtime.yaml`. Diseñar cómo llega un bundle al pool (volumen, imagen o
  descarga desde la versión publicada). **(feature)**

### 7. Leia
- `schemas/nexus-api.md`: los ejemplos de respuesta de la era v0.3.0 (status, logs) quedaron
  marcados como viejos; reescribirlos con respuestas reales de 0.26.12.
- Pendientes de la auditoría: repasar la guía de patrones de orquestación contra core 0.65+
  (supervisor con tools `type: agent`), el hand-off hacia astromesh-sdd, y
  `docs/agents-guide.md` más allá de la línea de auth.

### 8. Cortex
- No hay vista ni formulario de Eval: solo schema y snippet, y nada en la app abre un
  `*.eval.yaml`. Requiere un navegador de archivos o un tipo de documento Eval.
- Sin UI para tools `client`, `rate_limit` ni limpieza de `spec.channels` / `observability`.
- Un `model.primary` legado sin `provider`/`source` se guarda como candidato
  `openai_compat`; el core lo ignora. Debería quedar intacto o avisar.
- CI: `npx tsc --noEmit` no chequea ningún archivo (el `tsconfig` raíz no lista ninguno).
  `tsc -p tsconfig.web.json` da 35 errores previos (tipos de Monaco, imports `?worker`).
  Arreglarlos y pasar CI a `-p tsconfig.web.json`.

### 9. Forge
- Sin formularios dedicados para `connection`/`actions` de tools `integration` ni para la
  definición de tools `api`/`mcp` (hoy viajan intactas como YAML).
- Un `primary` legado con solo `providerRef` lo descarta el core en silencio; Forge debería
  avisar y ofrecer pasarlo a la forma por roles.

## P3 — Deuda de proceso y librerías

### 10. Lint de sub-paquetes
- CI no corre `ruff` sobre `astromesh-adk/` ni `astromesh-cli/`, y hay archivos sin
  formatear de antes. Formatear una vez y sumar ambos al job de lint de `ci.yml`.

### 11. Librerías propias
- astromesh-rag: registrar el trusted publisher de PyPI (manual), correr el benchmark real
  (falta URL y key de la pasarela) y después migrar el core a usarla.
- astromesh-okf: menores pendientes del 0.1.0.
- astromesh-glyph: el publish a TestPyPI falla siempre (sin trusted publisher, ver `DEBT.md`).

### 12. Fuera de astromesh
- `fainansu-platform`: `develop` lleva 9 commits de deploy/prod sobre `main` (incluye "prod
  phase 1" y Traefik HTTPS). Llevar a `main` solo con OK explícito.

## Cómo mantener la paridad la próxima vez

Cortex (schema e inspectores), Forge (listas de providers, tools y modelo) y el runner del
ADK están mantenidos a mano. En cada cambio del manifiesto en el core: auditar los tres
contra `astromesh/runtime/engine.py`, actualizar Leia (`schemas/`) y docs-site, y recién
después sacar los releases en este orden: core → CLI → node → ADK → Cortex → Leia → Nexus →
docs-site (`develop` → `main`).
