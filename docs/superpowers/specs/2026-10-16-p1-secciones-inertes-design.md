# P1 — Secciones inertes, confirmación local en el ADK y `blocked` persistido en Nexus

> Estado: diseño, 2026-10-16. Origen: P1 de
> `docs/superpowers/plans/2026-10-16-pendientes-ecosistema.md`. El usuario delegó todas las
> decisiones ("salteá las preguntas, decidí vos"): todo lo de abajo es decisión mía, con su
> motivo, salvo donde se cita al usuario. Hechos de base: `.claude` job report `p1-facts.md`
> (resumido en cada sección).

## Intención

Hoy el core **acepta en silencio** secciones del manifiesto que no hacen nada. Quien declara
`permissions.allowed_actions` cree que restringió las tools y no restringió nada; quien declara
memoria semántica cree que el agente recuerda y no recuerda. Es el mismo problema que tuvieron
los guardrails hasta 0.70.0. La regla de esta ronda: **ninguna sección del manifiesto se acepta
sin efecto**. Cada una se implementa o se rechaza con un error claro al cargar.

Además, dos huecos que hacen que la misma corrida se comporte distinto según por dónde entra:
el ADK local no tiene la compuerta de confirmación ni `mode: propose`, y Nexus no guarda que
una corrida fue bloqueada por un guardrail.

### Uso real (medido, define el riesgo)

- Nexus dev (184 versiones, 31 live) y mvp (176, 10 live): **ninguna** versión usa
  `permissions`, `memory.semantic`, `memory.episodic`, `swarm` ni `timeout_seconds`.
- `timeout_seconds` sí se usa fuera de Nexus: `fainansu-agents` (120, con test de contrato) y
  Clarus Atlas lo escribe (60) en cada agente que genera. 20 de 21 manifiestos del repo lo
  declaran (30–90 s).
- Manifiestos y templates del repo usan `allowed_actions` (con nombres que no coinciden con sus
  tools) y `memory.semantic` (`sales-qualifier`, `brand-chef`, `support-agent`).

## Objetivos

1. `permissions.allowed_actions` / `denied_actions` restringen de verdad qué tools ve y puede
   ejecutar el agente.
2. `memory.semantic` y `memory.episodic` funcionan: se construyen desde el manifiesto, se
   escriben y se recuperan en el contexto.
3. `swarm` hace handoff real entre agentes.
4. `orchestration.timeout_seconds` corta la corrida.
5. ADK local: `@tool(requires_approval=True)` / `confirm` y `mode: propose` se comportan como en
   el core.
6. Nexus guarda `blocked` y `guardrail` en la invocación y los expone en
   `GET …/invocations/:id` y `/logs`.
7. Cortex, Forge, Leia y docs-site dejan de marcar estas secciones como inertes y las editan /
   documentan como funcionan.

## No-objetivos

- Permisos por rol de usuario o por tenant (sigue siendo estático por manifiesto).
- Filtrar argumentos de tools (fuera de alcance, igual que en 0.70.0).
- Un motor de memoria nuevo: se usan los backends que ya existen en `astromesh/memory/backends/`.
- Resumir episodios con un LLM: un episodio es un registro estructurado, sin llamada extra.
- Streaming local completo en el ADK (sigue siendo solo `done`).

## Anti-objetivos (sería un fracaso aunque funcione)

- Que un manifiesto que hoy carga y anda deje de cargar sin un mensaje que diga qué cambiar.
- Que `api.main` deje de importar sin extras (rompe la imagen de astromesh-os): todo backend de
  memoria se importa de forma perezosa.
- Que un agente con `allowed_actions` quede con cero tools sin aviso.
- Romper el caché de prompts sin avisar (el engine ya advierte por `memory.semantic/episodic`
  en el system prompt; se mantiene).

## Diseño (decisiones)

### 1. Permisos — implementar

- `allowed_actions: [patrón, …]`: whitelist de **nombres de tool registrados**, con comodines
  `fnmatch` (stdlib) para cubrir tools con nombre derivado (`<slug>_<acción>` de
  integration/api/mcp, `kb_*`). Si la clave está presente, una tool que no matchea ningún
  patrón no se ofrece al modelo.
- `denied_actions: [patrón, …]`: se aplica después; gana sobre `allowed_actions`.
- Doble punto de aplicación: (a) `get_tool_schemas` no la ofrece; (b) en `tool_fn` una llamada
  a una tool no permitida no se ejecuta y vuelve como observación de error
  (`"tool '<n>' no permitida por permissions"`), con span/atributo de traza. (b) cubre modelos
  que inventan nombres.
- Al cargar: warning por cada patrón que no matchea ninguna tool registrada, y warning fuerte si
  el resultado deja al agente sin tools habiendo declarado tools.
- El mecanismo viejo (`ToolDefinition.permissions`, nunca seteado) se elimina.
- Cualquier otra clave bajo `permissions` se reporta con el aviso de claves ignoradas que ya
  existe (`claves_ignoradas`).
- Manifiestos y templates del repo: corregir `allowed_actions` para que nombren sus tools reales.

### 2. Memoria semántica y episódica — implementar

Casi todo existe: `MemoryManager` ya busca y guarda en semántica y recupera episodios; los
backends existen. Falta el cableado.

- `memory/factory.py` construye `semantic` (`chromadb` | `faiss` | `pgvector` | `qdrant`) y
  `episodic` (`postgres`) desde el manifiesto; import perezoso, error claro si falta el extra
  (`pip install astromesh[chromadb]`).
- Embeddings: `memory.semantic.embeddings` con el mismo shape que el embedder de RAG, reusando
  `rag/factory.py::_build_embedder` (ollama / hf / sentence_transformer). Sin `embeddings` →
  `AgentConfigError` (no hay default implícito que llame a un servicio).
- Escritura semántica: la que ya hace `persist_turn` (turnos del asistente > 50 tokens).
- Episodio = un registro por corrida terminada: `query` (truncada), resultado (`ok` |
  `blocked` | `error` | `timeout`), tools llamadas, tokens, regla de guardrail si hubo bloqueo.
  Se escribe al persistir el turno; una corrida bloqueada en input también deja episodio (sin la
  query, que puede tener PII).
- Al prompt llegan proyecciones seguras: `memory.semantic` = lista de
  `{content, similarity, source}` (sin el vector), `memory.episodic` = lista de dicts del
  episodio. Se recomienda usarlas en `prompts.context`, no en `system` (el warning de caché
  sigue).
- Falla del backend en runtime: se loguea y la corrida sigue sin esa memoria (igual que hoy con
  conversacional).

### 3. Swarm — implementar con el cableado del supervisor

- Los agentes del swarm se declaran como tools `type: agent` (igual que los workers del
  supervisor desde 0.65). Handoff = el modelo llama a la tool del agente destino.
- Diferencia con supervisor: en swarm la respuesta del agente al que se le pasó el control **es
  la respuesta final** (no vuelve al agente que delegó), y el destino recibe la historia de la
  conversación. Un tope `max_handoffs` (default 3) evita ciclos.
- Sin tools `type: agent` → `AgentConfigError` (igual que supervisor).

### 4. `timeout_seconds` — implementar, con aviso

- `asyncio.wait_for` alrededor de la ejecución del pattern en `Agent.run`. Sin la clave, sin
  timeout (comportamiento actual). Al vencer: corrida cortada, respuesta con
  `error: "timeout"` y HTTP 504 en `/v1/agents/{name}/run`; el episodio la registra.
- Riesgo: 20 manifiestos del repo declaran 30–90 s y empiezan a cortarse. Se revisan y se suben
  donde haga falta; el CHANGELOG lo marca como **cambio de comportamiento**.
- Los timeouts de provider HTTP siguen aparte.

### 5. ADK local — reusar la compuerta del core

- Mover la lógica de la compuerta (bloque de `tool_fn` + `_aviso_confirmacion`) de `engine.py`
  a `runtime/confirmacion.py` como funciones reutilizables, sin cambiar comportamiento del core
  (tests existentes como red).
- `ADKRuntime` mantiene un `Pendientes` propio y llama a esas funciones desde su `tool_fn`;
  `@tool(requires_approval=True)` se mapea a `confirm`.
- `mode: propose`: las tools de escritura no se ejecutan y se devuelven en
  `RunResult.propuestas`, igual que en el core. Requiere pasar el contexto de corrida a las
  tools del ADK.
- API para confirmar en local: la misma forma que la remota (re-correr con la confirmación),
  documentada en el ADK.

### 6. Nexus — persistir el bloqueo

- Columnas `blocked boolean not null default false` y `guardrail jsonb null` en `invocations`,
  agregadas con el `ALTER TABLE` protegido por catálogo de `PostgresStore.migrate()`.
- `CloseInvocation` las escribe; las cuatro SELECT, `scanInvocation` y `clientInvocation` las
  leen. El JSON al cliente es aditivo (`blocked` solo si true, como en `/run`), así que Cortex no
  se rompe.
- `/logs` muestra el bloqueo. Leia `/leia logs` lo muestra.

### 7. Herramientas y docs

- Cortex: schema e inspectores para `permissions` (lista de patrones con autocompletado de
  tools), memoria semántica/episódica con `embeddings`, swarm sin la marca de inerte,
  `timeout_seconds` de vuelta en el inspector de orquestación.
- Forge: lo mismo en el canvas/wizard (al menos sin marca de inerte y round-trip).
- Leia: schemas de manifiesto al día.
- docs-site: quitar las notas "no se aplica" y documentar el comportamiento.

## Restricciones

- Python 3.12, `ruff check` + `ruff format --check` antes de pushear; CHANGELOG en cada
  feat/fix (regla del CLAUDE.md del core).
- Release: core **0.71.0** (minor, cambio de comportamiento documentado en "Breaking for
  existing manifests"), ADK 0.6.0, Nexus 0.26.13 (+ pool en 0.71.0), OS pin, Cortex 0.27.0,
  Forge 0.28.0, Leia 0.9.0, docs-site.
- `api.main` importa sin extras (boot gate de astromesh-os).
- Trailer de commit exacto: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Lo que queda al builder

Nombres internos, estructura de tests, forma exacta del span de "tool no permitida", y el
orden de tareas, siempre que cada parte se pueda revisar por separado.
