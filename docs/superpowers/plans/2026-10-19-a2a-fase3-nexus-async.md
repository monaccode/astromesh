# A2A Fase 3 — Tareas asíncronas y push en Nexus · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tareas A2A largas en Nexus: envío no bloqueante, suscripción a una tarea en curso, cancelación entre pods y notificaciones push seguras.

**Architecture:** Sobre `internal/a2a/` de la fase 1. Ejecución en background con su propio contexto y registro en `invocations`; eventos de la tarea persistidos en una tabla nueva para `SubscribeToTask`; cancelación por bandera en el store que el ejecutor consulta; push con egress pineado a IP pública y JWT firmado.

**Tech Stack:** Go 1.25.3, a2a-go/v2, Postgres.

**Spec:** `D:/monaccode/_wt/astromesh-a2a/docs/superpowers/specs/2026-10-19-a2a-design.md` §4 fase 3. **Depende de:** fase 1 en `develop`.

## Global Constraints

- `configuration.returnImmediately: true` (o `blocking: false` según la binding del SDK) → respuesta inmediata `TASK_STATE_SUBMITTED`; la corrida sigue en background con el mismo `RunTimeout`.
- Eventos persistidos en `a2a_task_events (invocation_id, seq, kind, payload jsonb, created_at)`; `SubscribeToTask` reenvía desde `seq` y sigue en vivo; retención 24 h (barrido existente `SweepStale` extendido).
- Cancelación: columna `cancel_requested_at` en `invocations`; el ejecutor la consulta cada ≤2 s; `CancelTask` de cualquier pod la marca.
- Push: `CreateTaskPushNotificationConfig` sólo si `NEXUS_A2A_PUSH=true`; URL https obligatoria, resolución a IP pública (bloquear 10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, 100.64/10, ::1, fc00::/7, fe80::/10, IPv4-mapped), sin redirecciones, timeout 10 s, 3 reintentos con backoff; cuerpo firmado con JWT (HS256 con secreto por config) en `Authorization: Bearer`; capacidad `pushNotifications` en la card sólo si está habilitado.
- Migración aditiva; gates como la fase 1.

## Review Focus

1. **Pod que muere** con una tarea en background: `SweepStale` la pasa a `timeout`/`FAILED` y los suscriptores reciben el estado final. → `TestTareaHuerfanaFalla` (T1).
2. **Push a una URL que resuelve a 169.254.169.254**: bloqueado, nunca se conecta. → `TestPushMetadataBloqueado` (T3).
3. **Suscriptor que llega tarde** (tarea ya terminada): recibe el historial y el estado final, y el stream cierra. → `TestSubscribeTareaTerminada` (T2).
4. **Cancelación pedida en otro pod**: la corrida se detiene en ≤2 s y queda `cancelled` sin cargo. → `TestCancelEntrePods` (T1).
5. **Push config de otro tenant**: no listable ni borrable. → `TestPushConfigOtroTenant` (T3).

---

### Task 1: Ejecución en background y cancelación entre pods

**Files:** `internal/a2a/background.go`, migración (`internal/store/postgres.go` patrón existente), `internal/store/invocations.go` (`cancel_requested_at`), tests.

- [ ] **Step 1: Tests que fallan:** `TestReturnImmediatelySubmitted`; `TestBackgroundCompletaYFactura`; `TestCancelEntrePods`; `TestTareaHuerfanaFalla`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS. **Step 5:** Commit `feat(a2a): tareas en background y cancelación entre pods`.

### Task 2: Eventos persistidos y `SubscribeToTask` / `ListTasks`

**Files:** `internal/a2a/events.go`, migración `a2a_task_events`, tests.

- [ ] **Step 1: Tests que fallan:** `TestSubscribeEnVivo`; `TestSubscribeTareaTerminada`; `TestListTasksDelTenant`; `TestRetencion24h`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS. **Step 5:** Commit `feat(a2a): SubscribeToTask y ListTasks`.

### Task 3: Notificaciones push seguras

**Files:** `internal/a2a/push.go`, `internal/netguard/` (egress pineado reutilizable), migración `a2a_push_configs`, tests.

- [ ] **Step 1: Tests que fallan:** `TestPushEntregaFirmada` (httptest con IP pública simulada vía resolver inyectable); `TestPushMetadataBloqueado`; `TestPushSinRedirecciones`; `TestPushReintentos`; `TestPushConfigOtroTenant`; `TestCardAnunciaPushSoloSiHabilitado`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS. **Step 5:** Commit `feat(a2a): notificaciones push con egress seguro`.

### Task 4: Interop, docs y release

- [ ] **Step 1:** Interop con `astromesh-a2a` (stream + polling + cancel). **Step 2:** Docs y CHANGELOG. **Step 3:** `/deploy-dev` → `/deploy-mvp`.
