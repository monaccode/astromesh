# A2A Fase 1 — Nexus como servidor A2A · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que cada agente publicado en Nexus que lo habilite sea un agente A2A 1.0: Agent Card autenticada, `SendMessage`, `SendStreamingMessage` (SSE), `GetTask` y `CancelTask`, con la Task respaldada por la invocación de Nexus.

**Architecture:** Paquete nuevo `internal/a2a/` que implementa las interfaces de `github.com/a2aproject/a2a-go/v2` (executor + task store) sobre `prepareRun`/runtime/invocations existentes, montado bajo `/a2a/v1/agents/:name` con `DualAuthMiddleware`. La corrida se envía al nodo con `origen: "agente"`.

**Tech Stack:** Go 1.25.3, gin, `github.com/a2aproject/a2a-go/v2` v2.6.0, database/sql + pgx.

**Spec:** `D:/monaccode/_wt/astromesh-a2a/docs/superpowers/specs/2026-10-19-a2a-design.md` §4 fase 1.

**Rama:** `feat/a2a` (worktree `D:/monaccode/_wt/nexus-a2a`, desde `origin/develop` v0.26.13). Go vía Docker: `C:/Users/jfulf/.claude/jobs/5687a937/tmp/ngo <args>`.

## Global Constraints

- Exponer es **opt-in por agente**: `spec.a2a.publicar: true` en el spec del agente; sin eso, todas las rutas A2A del agente devuelven 404 idéntico al de agente inexistente.
- Rutas: `GET /a2a/v1/agents/:name/.well-known/agent-card.json` y `POST /a2a/v1/agents/:name` (JSON-RPC, SSE para streaming). Ambas con `DualAuthMiddleware` (tenant del JWT/API key). No hay rutas A2A sin auth en esta fase.
- Card: `name`, `description` (`spec.identity.description`), `version` (número de versión de Nexus), `supportedInterfaces: [{url, protocolBinding: "JSONRPC", protocolVersion: "1.0"}]`, `capabilities {streaming: true, pushNotifications: false}`, `skills` desde `spec.skills` (fase 0), `securitySchemes` (`apiKey` en header `X-API-Key` y `bearer` JWT), `defaultInputModes`/`defaultOutputModes` `["text/plain","application/json"]`.
- Mapeo de estados: `in_progress→TASK_STATE_WORKING`, `ok→TASK_STATE_COMPLETED`, `error|timeout→TASK_STATE_FAILED`, `cancelled→TASK_STATE_CANCELED`, `rejected→TASK_STATE_REJECTED`. `contextId` ↔ `session_id` (sin prefijo de namespace hacia afuera). `taskId` = `invocation_id`.
- Toda corrida A2A manda `origen: "agente"` al nodo (campo de la fase 0; un nodo viejo lo ignora).
- Admisión, límites de plan, créditos y facturación: los mismos de `prepareRun` (una corrida A2A es una invocación más; `Adapter = "a2a"`).
- Header `A2A-Version`: aceptar `1.0`; otro → `VersionNotSupportedError`.
- Gate por commit: `ngo build ./... && ngo vet ./... && ngo test ./...` (con `TEST_DATABASE_URL` para el store) y golangci-lint v2.8.0 sin hallazgos nuevos. Nunca `go fmt ./...` sobre todo el árbol (CRLF); `gofmt -l` sólo en archivos tocados.
- CHANGELOG `[Unreleased]`; release con `/deploy-dev` y `/deploy-mvp` del repo al final.

## Review Focus

1. **Agente sin `a2a.publicar`** consultado por A2A: 404 idéntico al inexistente, sin tocar el runtime. → `test_agente_no_publicado_404` (T3).
2. **API key de otro tenant** pidiendo la card de un agente ajeno: 404 (no 403). → `test_card_de_otro_tenant_404` (T3).
3. **Cliente que corta el SSE** a mitad: la invocación queda `cancelled` y no se factura (igual que el WS). → `test_sse_desconexion_cancela` (T5).
4. **`GetTask` de un `taskId` de otro tenant**: `TaskNotFoundError`. → `test_gettask_otro_tenant` (T6).
5. **Idempotencia**: el mismo `messageId` repetido no dispara dos invocaciones. → `test_messageid_idempotente` (T4).

---

### Task 1: Spike de `a2a-go/v2` → ADR

**Files:** `docs/adr/a2a-go.md` (o la carpeta de decisiones que use el repo).

- [ ] **Step 1:** `ngo get github.com/a2aproject/a2a-go/v2@v2.6.0` en una rama descartable; leer paquetes servidor (`a2asrv` o equivalente: interfaces de executor, task store, request handler, handler JSON-RPC sobre `net/http`, SSE), tipos (`a2a.AgentCard`, `a2a.Task`, `a2a.Message`, `TaskState`) y cómo montar el handler en gin (`gin.WrapH`).
- [ ] **Step 2:** ADR: firmas exactas que usarán T3-T6, cómo se inyecta el tenant/autorización por request, si el SDK maneja `A2A-Version`, y qué parte del task store se implementa sobre `invocations`. Commit `docs(adr): superficie de a2a-go que usamos`.

### Task 2: `origen` hacia el runtime

**Files:** `internal/runtime/client.go` (`runPayload` ~L176-182, stream payload), `internal/runtime/client_test.go`.

**Interfaces:**
- Produces: `runtime.RunRequest` (o el struct que use) gana `Origen string \`json:"origen,omitempty"\``; `""` no se envía (compatibilidad).

- [ ] **Step 1: Tests que fallan:** `TestRunPayloadOrigenAgente` (httptest captura el body: `origen == "agente"`); `TestRunPayloadSinOrigenOmiteCampo`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS. **Step 5:** Commit `feat(runtime): origen del turno hacia el nodo`.

### Task 3: Agent Card por agente

**Files:** `internal/a2a/card.go`, `internal/a2a/card_test.go`, `internal/server/server.go` (grupo `/a2a/v1` con `DualAuthMiddleware`).

**Interfaces:**
- Produces: `func BuildCard(agent store.Agent, version store.AgentVersion, baseURL string) (a2a.AgentCard, bool)` (el bool = publicado); handler `GET /a2a/v1/agents/:name/.well-known/agent-card.json`.

- [ ] **Step 1: Tests que fallan:** `TestCardDesdeSpec` (skills, description, version, interfaces, securitySchemes); `test_agente_no_publicado_404`; `test_card_de_otro_tenant_404`; `TestCardSinAuth401`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar (base URL desde config `NEXUS_PUBLIC_URL`, documentar). **Step 4:** → PASS. **Step 5:** Commit `feat(a2a): agent card por agente publicado`.

### Task 4: `SendMessage` bloqueante = invocación

**Files:** `internal/a2a/executor.go`, `internal/a2a/store.go`, `internal/a2a/executor_test.go`, `internal/server/handlers/invocations.go` (extraer de `prepareRun` lo reusable sin cambiar su comportamiento para REST/WS).

**Interfaces:**
- Consumes: ADR (T1), `origen` (T2), card (T3).
- Produces: handler `POST /a2a/v1/agents/:name` método `SendMessage` → `Task` final (`COMPLETED` con artefacto texto + `data` si la corrida devolvió datos; `FAILED` con mensaje sin detalles internos); `Adapter = "a2a"` en la invocación.

- [ ] **Step 1: Tests que fallan** (runtime falso): `TestSendMessageCompleta`; `TestSendMessageFalla`; `TestSendMessageAdmisionRechaza` (sin créditos → `TASK_STATE_REJECTED`); `TestSendMessageMandaOrigenAgente`; `test_messageid_idempotente` (`messageId` → `Idempotency-Key` interno); `TestVersionHeaderNoSoportada`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS (incluye tests del store con DB). **Step 5:** Commit `feat(a2a): SendMessage sobre invocaciones`.

### Task 5: `SendStreamingMessage` (SSE)

**Files:** `internal/a2a/stream.go`, `internal/a2a/stream_test.go`.

**Interfaces:**
- Consumes: `rt.RunStream` (`runtime/stream.go:55`).
- Produces: SSE `text/event-stream` con `StreamResponse`: `statusUpdate WORKING` → `artifactUpdate` por cada `token` (append) → `statusUpdate COMPLETED|FAILED` final con el mismo cierre de facturación que `StreamRun`.

- [ ] **Step 1: Tests que fallan:** `TestStreamOrdenDeEventos`; `test_sse_desconexion_cancela` (status `cancelled`, sin cargo); `TestStreamErrorDelRuntime`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS. **Step 5:** Commit `feat(a2a): streaming por SSE`.

### Task 6: `GetTask` y `CancelTask`

**Files:** `internal/a2a/tasks.go`, `internal/a2a/tasks_test.go`.

**Interfaces:**
- Produces: `GetTask(id)` desde `invocations` (mapeo de estados de Global Constraints; historial no se guarda en esta fase → `history: []`); `CancelTask(id)` cancela una corrida en vuelo **en este pod** (registro en memoria de cancel funcs, como el WS); si no está en vuelo aquí → `TaskNotCancelableError` (la cancelación entre pods es fase 3).

- [ ] **Step 1: Tests que fallan:** `TestGetTaskMapeaEstados` (tabla con los 5 estados); `test_gettask_otro_tenant`; `TestCancelTaskEnVuelo`; `TestCancelTaskTerminadaNoCancelable`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS. **Step 5:** Commit `feat(a2a): GetTask y CancelTask`.

### Task 7: Interop, docs y release

**Files:** `test/a2a_interop/` (script Python que usa `astromesh-a2a` `RemoteAgent` contra un Nexus de prueba levantado con docker-compose; se corre en CI sólo si el job lo habilita — si no, documentar el comando), `docs/` del repo (sección A2A: cómo habilitar `spec.a2a.publicar`, URL de la card, auth), `CHANGELOG.md`.

- [ ] **Step 1:** Correr el interop una vez localmente contra el Nexus de la rama (requiere `astromesh-a2a` publicada o instalada desde su repo) y pegar la salida en el reporte.
- [ ] **Step 2:** Docs + CHANGELOG. Commit `docs(a2a): exponer agentes por A2A`.
- [ ] **Step 3:** Merge a `develop` (PR) → `/deploy-dev` → `/deploy-mvp`.
