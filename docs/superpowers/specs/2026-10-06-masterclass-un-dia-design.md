# Masterclass FDE en un día: temario, repo del curso y RAG en la Academia

**Fecha:** 2026-10-06
**Estado:** diseño aprobado en conversación; pendiente de revisión del spec escrito.
**Alcance:** tres repos.

| Parte | Repo | Entregable |
|---|---|---|
| 1 | `monaccode/astromesh-academia` | Documentos en el mundo, `GET /api/mundo/documentos`, escenario `consulta_documento` |
| 2 | `monaccode/astromesh-taller-fde` (nuevo, público) | Repo del curso, incremental por tags, Docker local; artefacto con su diseño |
| 3 | `monaccode/astromesh` (`social/masterclass-fde.html`) | Artefacto del temario reescrito |

Orden de construcción: 1 → 2 → 3. El repo necesita el escenario RAG; el temario cita el repo.

## Intención

La masterclass «De Software Engineer a Forward Deployed Engineer» pasa a **un día completo
(09:00–18:00) con un break de almuerzo**. CLARUS sale del curso. El alumno recorre lo que
significa tener un agente corriendo —que no es sólo un LLM— construyendo cada pieza del
harness **desde cero**, viendo qué paquete del mercado la resuelve y cómo la resolvió
Astromesh. Las novedades del core 0.64.0 (presupuesto de contexto, resumen incremental,
`prompts.context`, `cache.hit_ratio`) son protagonistas donde corresponden.

**Éxito:** al final del día cada alumno tiene un harness propio, corriendo en Docker en su
máquina, que pasa los escenarios del verificador de la Academia, y sabe qué pieza resuelve qué.

## El día: 8 estaciones

Las estaciones son los 8 distritos de la Academia.

| # | Estación | Hora | El alumno construye | Paquete de referencia | Astromesh | Escenario |
|---|---|---|---|---|---|---|
| 1 | Muelle | 09:00–09:50 | Setup del proyecto para IA (AGENTS.md, CLAUDE.md, una skill, Claude Code/Codex/Kimi Code); `/run` responde. Rol FDE y nacimiento de Astromesh en 10 min | — | CLAUDE.md y skills del propio repo | `harness_responde` |
| 2 | Forja | 09:50–11:00 | Loop con tope, tools con schema, agente como YAML | OpenAI Agents SDK, Pydantic AI | 7 patrones, ToolRegistry | `consulta_producto` |
| 3 | Mercado | 11:00–11:50 | Router: proveedor, fallback, circuit breaker, costo por llamada | LiteLLM, OpenRouter | ModelRouter, modelo por rol | `fallback_modelo_retirado` |
| 4 | Archivo | 11:50–13:00 | RAG: chunking, embeddings, índice pgvector, recuperación, «no sé» | LlamaIndex, Haystack | 4 chunkers, 4 vector stores, rerank | `consulta_documento` (nuevo) |
| — | Almuerzo | 13:00–14:00 | | | | |
| 5 | Ascensor | 14:00–15:10 | Contexto por niveles: system → tools → historial con presupuesto → contexto del turno → query; resumen incremental; prefijo cacheable | Mem0, Letta, prompt caching; DSPy como noción | **0.64.0**: `context_window`, `tokens.py`, `strategy: summary`, `prompts.context` | `memoria` |
| 6 | Aduana | 15:10–16:00 | Compuertas: confirmación en código, guardrails, prefetch | Guardrails AI, NeMo, Presidio | Confirmación, modo propose, prefetch | `sin_confirmacion_no_se_escribe` |
| 7 | Torre | 16:00–16:50 | Trazas, tokens, `cache.hit_ratio`, costo por corrida | Langfuse, OpenTelemetry | Spans `llm.complete` y `context_fit` (**0.64.0**) | `traza_coincide` |
| 8 | Bolsa | 16:50–18:00 | Costo por unidad y precio; la nube como noción (Prisma 10/17/7); pitch; Momento Superinteligencia 3 | — | Nexus: medición y techo de gasto | `costo_por_unidad` |

Se pierden frente al temario de 8 encuentros: la práctica en la nube (queda como noción) y
el ecosistema/sub-agentes (menciones).

## Parte 1 — RAG en la Academia

- `content/mundo/documentos/*.md`: 6 a 8 documentos de la Ferretería Orbital (ficha de la
  epoxi con tiempo de curado, política de garantía, manual del taladro percutor, guía de
  tarugos por material, envíos a otros módulos de la estación). Cada uno con al menos un
  dato que no está en `productos.yaml`.
- `GET /api/mundo/documentos` → `[{id, titulo, contenido}]`. Misma autenticación que el
  resto de `/api/mundo` (clave del participante).
- Escenario `consulta_documento`, dos preguntas en sesiones distintas:
  1. Pregunta cuya respuesta sólo está en un documento → pasa si la respuesta contiene el
     dato (comparación normalizada, tolerante a formato: «72 horas», «72 h»).
  2. Pregunta que ningún documento responde → pasa si la respuesta no afirma un dato inventado
     y declara no saberlo (lista de expresiones aceptadas: «no tengo», «no sé», «no encuentro»,
     «no figura»…). Falla si contiene un número o plazo para lo preguntado.
- Se retira `nube_misma_bateria` (código, tests y referencias en quests).
- La quest de Archivo (`m1.yaml` hoy es «Nacimiento») se reasigna. **Las quests y
  `curso.yaml` (pasar a 1 día) quedan fuera de este spec**: seguimiento propio. Este spec sólo
  agrega el escenario y los documentos, y el `harness-referencia` gana RAG para seguir siendo
  la solución modelo (pasa `consulta_documento`).

## Parte 2 — Repo `monaccode/astromesh-taller-fde`

Público. Licencia MIT (código) y CC BY 4.0 (textos de `estaciones/*/README.md`). Python 3.12,
`uv`, FastAPI.

### Estructura

```
astromesh-taller-fde/
  AGENTS.md                # reglas del proyecto para cualquier agente de código
  CLAUDE.md                # @AGENTS.md + específico de Claude Code
  .agents/skills/nueva-tool/SKILL.md
  .claude/skills/nueva-tool/SKILL.md
  compose.yaml  Dockerfile  .env.example  .gitattributes  pyproject.toml  uv.lock
  taller/                  # comandos del curso, corren en el contenedor: probar, verificar
  harness/
    app.py                 # POST /run, contrato de la Academia
    loop.py  tools.py  agente.yaml
    router.py              # desde Mercado
    rag/                   # desde Archivo: indexar.py, buscar.py
    contexto.py            # desde Ascensor
    compuertas.py          # desde Aduana
    trazas.py  costos.py   # desde Torre / Bolsa
  estaciones/N-nombre/
    README.md              # consigna · paquete de referencia · cómo lo hizo Astromesh
    referencia/            # ~30 líneas con el paquete del mercado
    tests/                 # lo que harness/ tiene que pasar
  .github/workflows/ci.yml
```

### Incremental

- Tag `estacion-N`: estaciones 1..N-1 resueltas + esqueleto de N (con `NotImplementedError`
  y tests en rojo). `main` = todas resueltas. Tag `estacion-1` es el punto de partida.
- Los tags se construyen en orden: cada uno es un commit sobre el anterior.
- `compose.yaml` crece con los tags:

| Desde | Servicio | Para qué |
|---|---|---|
| Muelle | `harness` | FastAPI con recarga, `:8080`, código montado como volumen |
| Archivo | `postgres` (pgvector) | Índice RAG; desde Ascensor también la memoria |
| Archivo | `ollama` | Sólo embeddings (`nomic-embed-text`); no hay modelo de chat local |
| Torre | `jaeger` | OTLP y UI en `:16686` |
| siempre | `tunel` (cloudflared, perfil) | Exponer el harness al verificador |

### Modelo y costo

- Chat: Kimi a través de la pasarela de la Academia (OpenAI-compatible). La key de Kimi del
  taller se carga en la pasarela antes del día y se rota al terminar; nunca llega a las máquinas.
  Cada alumno usa su clave personal de la Academia, que se entrega en el Muelle (techo USD 5).
- Fallback (Mercado): `kimi-k2.6` → `kimi-k2.7-code-highspeed`, ambos por la pasarela, que
  puede retirar el principal por alumno (así lo prueba `fallback_modelo_retirado`).
- Embeddings (desde Archivo): Ollama local con `nomic-embed-text`.
- Tests: modelo falso guionado, sin red, sin costo.

### Comandos

Los alumnos usan Linux, Mac y Windows. Sólo se instalan Docker, git y el agente de código;
todo lo demás vive en contenedores. **No hay `Makefile` ni scripts de shell en el host**: los
comandos del curso corren dentro del servicio `taller` (misma imagen que `harness`).

- `docker compose up -d` — levanta todo; desde Archivo, un servicio de una sola vez baja el modelo de embeddings.
- `docker compose run --rm taller probar N` — tests de la estación N.
- `docker compose run --rm taller verificar` — ruff + tests de las estaciones hasta la actual.
- `docker compose --profile tunel up tunel` — cloudflared; imprime la URL.
- Rescate: `git checkout estacion-N` (git avisa si hay cambios; `git stash`).

### Linux, Mac y Windows

- Windows: Docker Desktop con WSL 2; se recomienda clonar dentro de WSL. Si se clona en
  `C:\`, el compose activa `WATCHFILES_FORCE_POLLING=true` para la recarga.
- `.gitattributes` con `* text=auto eol=lf`: nada clonado en Windows se rompe en el contenedor.
- Linux: `extra_hosts: ["host.docker.internal:host-gateway"]` en el compose.
- Ollama corre con CPU en los tres sistemas; alcanza para embeddings.
- Skills como copias, no symlinks.
- Todas las imágenes multi-arquitectura (amd64 y arm64).
- CI levanta el compose sólo en `ubuntu-latest` (los runners de Mac no traen Docker y los de
  Windows corren contenedores Windows). Mac y Windows se prueban a mano en máquinas reales la
  semana de la clase.

### Requisitos del alumno

Docker Desktop (Mac, Windows con WSL 2) o Docker Engine (Linux), ~2 GB libres (imágenes + modelo de embeddings), git, la clave de la Academia (se entrega en el Muelle). Cualquier
agente de código; los tres de base son Claude Code, Codex y Kimi Code.

### Setup para IDEs de IA (Muelle)

- `AGENTS.md` es la fuente única de reglas. `CLAUDE.md` la importa con `@AGENTS.md`.
- Una skill de ejemplo (`nueva-tool`) en las rutas que lee cada herramienta.
- **Lo que lee cada IDE (AGENTS.md, ubicación de skills) se verifica contra la documentación
  vigente de Claude Code, Codex y Kimi Code al implementar.** No se afirma de memoria.

### CI

GitHub Actions: `ruff check`, `ruff format --check` y los tests de todas las estaciones
contra `main`; un job por tag que verifica que los tests de las estaciones anteriores pasan
y los de la estación N fallan. Sin secretos: los tests usan el modelo falso.

### Artefacto de diseño del repo

Un artefacto aparte («Taller FDE: el repo») con la estructura, el mapa estación → archivos →
servicios del compose → tests → escenario, cómo arrancar y cómo rescatarse.

## Parte 3 — Artefacto del temario

Reescritura de `social/masterclass-fde.html` (mismo URL de artefacto):

- Sale CLARUS/PRESTO en todo el documento. Las cifras de Astromesh medidas en un agente de
  producción se citan sin nombrar el producto. Las líneas de LinkedIn se reescriben con
  cifras propias de Astromesh (Glyph, prefetch, caché 86–88%).
- Encabezado: 1 día, 09:00–18:00, un break, en la Academia.
- Nueva sección «El día» con la agenda.
- M0–M7 pasan a las 8 estaciones, cada una con la ficha *Construís / El mercado lo resuelve
  con / Astromesh lo resolvió así / El verificador comprueba*, y marca «Nuevo en 0.64» en
  Ascensor y Torre. Ascensor lleva el diagrama de niveles del prompt.
- Sección del repo con link al repo público y al artefacto de diseño.
- Se mantienen: tesis, ¿qué es un harness?, comparativa, postulación, SWE→FDE, «Qué no vamos
  a decir» (actualizada), «Para iterar» (actualizada).

## Fuera de alcance

- `curso.yaml` y quests de la Academia para 1 día (seguimiento propio).
- Práctica de despliegue en la nube.
- Juez de acciones, compresión de prompts (LLMLingua), DSPy: sólo como noción.

## Riesgos

- **Red del aula:** la primera descarga de imágenes y modelos es pesada. El README pide
  `docker compose up -d` antes del día.
- **Windows sin WSL 2** (virtualización bloqueada en máquinas corporativas): no funciona. Se
  pregunta en la postulación.
- **Escenario «no sé»:** la detección por expresiones puede dar falsos negativos; se ajusta
  con corridas reales del `harness-referencia`.
