# Pendientes del ecosistema tras la ronda de paridad con core 0.70.0

> Estado al 2026-10-16. La ronda dejó publicados: ADK 0.5.0, CLI 0.4.0 (PyPI), Forge 0.27.0,
> Cortex v0.26.0, Leia v0.8.0, Nexus 0.26.12 (dev + mvp) y docs-site. Lo de abajo quedó
> fuera **a propósito** o salió a la luz durante la ronda. Ordenado por prioridad; cada ítem
> dice dónde está, qué hay que hacer y cómo se verifica. Los marcados **(feature)** van por
> el pipeline completo (brainstorm → spec → plan → SDD); el resto son arreglos acotados.

## P1 — HECHO (2026-10-17/18)

Resuelto con el spec/plan `2026-10-16-p1-secciones-inertes*` y publicado: core 0.71.0
(permissions, memoria semántica/episódica por sesión, swarm con handoff real,
`timeout_seconds` → 504), ADK 0.6.0 (confirmación local y `mode="propose"`), CLI 0.4.1,
Forge 0.28.0, Cortex 0.27.0, Leia 0.9.0, Nexus 0.26.13 (`blocked`/`guardrail` persistidos,
timeout de core como `timeout`; dev y mvp), OS 0.13.8, docs-site.

Quedó diferido de esa ronda (menores, sin bloquear):
- ADK: un sub-agente **remoto** usado como tool puede ser confirmado por el modelo padre
  (documentado en el README); `ctx.call_tool` desde código del handler saltea compuerta y
  propose; los equipos devuelven `propuestas` vacío; sin timeout de corrida en local.
- Core: la memoria y el RAG quedan fuera del plazo de `timeout_seconds`; las ramas paralelas
  hermanas no se cancelan cuando una vence; un timeout de un sub-agente se reporta como del
  padre; el uso del agente destino del swarm no suma al del padre; los guardrails de entrada
  del destino del swarm corren dos veces (span extra); `_episodio` silencia errores de
  programación (debería loguear); `record_run` tipa el resultado como `str`.
- Nexus: un run cortado por timeout factura 0 tokens.
- Cortex: el schema no marca como requeridos `embeddings`/`dimension`/`connection.url`
  (el core sí los exige); sin aviso rojo por `dimension` faltante; `timeout_seconds`
  tipado entero (el core acepta número > 0); el total de tests de vitest varía entre
  corridas bajo carga (383/420/431, siempre verde).
- Schema del editor (vscode): mismas laxitudes que Cortex.

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
