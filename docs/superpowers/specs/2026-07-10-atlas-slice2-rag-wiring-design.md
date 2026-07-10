# CLARUS Atlas — Slice 2 (parte 1): Cableado de RAG en el runtime de astromesh

> **Contexto de roadmap.** Esto es la **primera pieza del Slice 2** de CLARUS Atlas.
> El Slice 1 (generador de blueprints, en `clarus-platform`) produce YAML de astromesh
> y un **reporte de capability-gaps** de lo que el runtime todavía no ejecuta:
> `approval` (HITL), `async` (pausa/resume durable) y `kb_wiring` (cablear KB/RAG).
> Este spec cierra **`kb_wiring`** — el gap más barato de los tres y autocontenido
> (no toca el executor de workflows). `approval` y `async` son specs/slices aparte
> y van después (approval depende de async durable).
>
> **Repo de trabajo:** `astromesh` (no `clarus-platform`). El único cambio en Clarus
> es un follow-up separado (ver §Follow-up en Clarus).

## Objetivo

Que un `Agent` de astromesh **recupere de su knowledge base en runtime** y responda
fundamentado en ella, a partir de un `RAGPipeline` declarado como recurso de primera
clase. Concretamente, cuando el Slice esté listo:

1. Un `*.rag.yaml` (`kind: RAGPipeline`) se **carga** al bootstrap del engine y queda
   en un registro por nombre.
2. Un `Agent` referencia esa pipeline por nombre (`spec.knowledge.pipeline`), y al
   correr **recupera top-k automáticamente** e inyecta el contexto al system prompt.
3. `POST /rag/ingest` y `POST /rag/query` **funcionan de verdad** (hoy son stubs), de
   modo que el KB se pueda poblar y probar punta a punta.
4. Los tools `rag_query` / `rag_ingest` (ya existentes pero colgados) **quedan activos**
   como bonus, porque comparten la misma pieza de resolución.

## Estado actual (con evidencia)

Veredicto del reporte de gaps del Slice 1: **LIBRARY-ONLY**. La librería existe completa;
falta todo el cableado. Verificado en el repo (`astromesh` 0.29.0 en disco; Clarus pinea
0.28.9 — este spec apunta al tip, superset):

- **La librería está completa.** `RAGPipeline` (chunk→embed→upsert / query→rerank) en
  `astromesh/rag/pipeline.py:18`. Piezas pluggables ya implementadas:
  - Chunkers: `RecursiveChunker`, `FixedChunker`, `SentenceChunker`, `SemanticChunker`
    (`astromesh/rag/chunking/*.py`).
  - Embedders: `OllamaEmbeddingProvider`, `HFEmbeddingProvider`,
    `SentenceTransformerProvider` (`astromesh/rag/embeddings/*.py`).
  - Stores: `PGVectorStore`, `QdrantStore`, `ChromaStore`, `FAISSStore`
    (`astromesh/rag/stores/*.py`).
  - Rerankers: `CrossEncoderReranker`, `CohereReranker` (`astromesh/rag/reranking/*.py`).
- **Falta el factory config→instancia.** No hay `build`/`from_config`/factory en
  `astromesh/rag/`. Nada mapea `chunking.strategy: recursive` → `RecursiveChunker`,
  `vector_store.backend: pgvector` → `PGVectorStore`, etc. **Es la pieza central.**
- **Falta el loader.** No hay parser de `kind: RAGPipeline` (el `WorkflowLoader` en
  `astromesh/workflow/loader.py` es el patrón exacto a espejar). El engine carga agentes
  y workflows al bootstrap pero nunca RAGPipelines.
- **El agente nunca recupera.** `AgentRunner.run` (`astromesh/runtime/engine.py:497`) no
  tiene ninguna referencia a `rag`/`retriev`/`embedding`. La memoria sí está cableada
  (`self._memory.build_context` en :517, `persist_turn` en :663) — **es el paralelo exacto
  a seguir**.
- **No hay campo de enlace Agent→RAG.** El `support-agent.agent.yaml` de ejemplo hasta
  dice en su prompt "usá la knowledge base", pero no existe ningún campo que lo enlace a
  la RAGPipeline `product-knowledge` que está al lado.
- **Los endpoints REST son stubs.** `POST /rag/ingest` devuelve siempre
  `{"status": "not_configured", "chunks": 0}` y `/rag/query` devuelve `[]`
  (`astromesh/api/routes/rag.py:16-24`); nunca instancian una pipeline.
- **Tools ya existentes pero colgados.** `RagQueryTool` (`rag_query`) y `RagIngestTool`
  (`rag_ingest`) están implementados y registrados
  (`astromesh/tools/builtin/rag.py`, `tools/builtin/__init__.py:18`), y leen
  `getattr(context, "rag_pipeline", None)`. Pero **nada puebla `ctx.rag_pipeline`** en
  producción (solo se setea en tests) → en runtime siempre devuelven "RAG pipeline not
  available". Comparten la misma pieza de resolución que falta.
- **No hay `rag.schema.json`.** Solo `agent.schema.json` y `workflow.schema.json` en
  `vscode-extension/schemas/`. `RAGPipeline` no tiene schema de validación.

## Decisiones de diseño (cerradas en el brainstorming)

1. **Retrieval: automático / always-on.** Al arrancar `run()`, se recupera top-k para el
   query y se inyecta al system prompt — espejo del cableado de memoria. Determinista,
   garantiza uso del KB, bajo riesgo. (El modo tool-based queda **gratis** como bonus vía
   los tools existentes, ver §Componentes; no es el camino primario.)
2. **Enlace: referencia por nombre.** El agente referencia un `kind: RAGPipeline` por
   `metadata.name`. Habilita KB compartido entre agentes y matchea lo que Atlas ya emite
   (artefactos RAGPipeline separados). Requiere loader + registro + resolución.
3. **Ingesta: mínima dentro.** Cablear `/rag/ingest` a `RAGPipeline.ingest()` real +
   seed manual por API. La **orquestación** de ingesta (fuentes, sync, re-index, watchers)
   queda fuera.

## Arquitectura y componentes

Pieza clave de coherencia: **una sola resolución alimenta dos consumidores.** Al construir
el agente se resuelve el nombre de la pipeline y se construye la instancia una vez; esa
instancia se expone como `self._rag` (inyección always-on) **y** como `ctx.rag_pipeline`
(activa los tools `rag_query`/`rag_ingest` ya existentes). Sin trabajo extra, los dos
paradigmas quedan servidos por el mismo cableado.

### 1. `RAGPipelineSpec` + `RAGPipelineLoader` (nuevo)
`astromesh/rag/loader.py`, espejo de `astromesh/workflow/loader.py`:
- `RAGPipelineSpec` — dataclass con la config parseada (`metadata.name`, `chunking`,
  `embeddings`, `vector_store`, `reranking`, `retrieval`).
- `RAGPipelineLoader.load_all(dir)` → `dict[str, RAGPipelineSpec]` cargando `*.rag.yaml`,
  validando `kind: RAGPipeline`, saltando archivos inválidos (mismo criterio best-effort
  que `WorkflowLoader`).
- El engine llama al loader al bootstrap (donde ya carga agentes/workflows) y guarda el
  registro `{name: RAGPipelineSpec}`.

### 2. Factory config→instancia (nuevo) — *pieza central*
`astromesh/rag/factory.py`:
- `build_pipeline(spec: RAGPipelineSpec) -> RAGPipeline` que mapea strings de config a las
  clases concretas ya existentes:
  - `chunking.strategy`: `recursive|fixed|sentence|semantic` → `*Chunker`.
  - `embeddings.provider`: `ollama|hf|sentence_transformer` → `*EmbeddingProvider`.
  - `vector_store.backend`: `pgvector|qdrant|chroma|faiss` → `*Store`.
  - `reranking` (si `enabled`): `cross_encoder|cohere` → `*Reranker`; si no, sin reranker.
- Registros explícitos (dict `str → clase`) con error claro ante un valor desconocido.
- Cada rama pasa la sub-config al constructor de la clase (los constructores concretos ya
  existen; el factory solo los conecta).

### 3. Resolución Agent→RAG (tocado: `runtime/engine.py`)
Donde hoy se construye la memoria
(`memory = MemoryManager(agent_id=..., config=spec.get("memory", {}))`, ~`engine.py:296`):
- Leer `spec.get("knowledge")`. Si trae `pipeline: <name>`:
  - Resolver `<name>` en el registro de RAGPipelines. Si no existe → log de warning y
    `rag = None` (no-fatal; ver §Errores).
  - `pipeline = build_pipeline(spec_resuelta)`; envolver en un `AgentRAG` liviano que
    guarda `pipeline` + `top_k` (default de `retrieval.top_k`, override por
    `spec.knowledge.top_k`).
- Guardar `self._rag = rag` en el `AgentRunner` (paralelo a `self._memory`).
- Adjuntar la instancia al `ToolContext` como `ctx.rag_pipeline` cuando se arma el contexto
  de tools (esto **activa** `rag_query`/`rag_ingest`). Agregar el campo `rag_pipeline` a
  `ToolContext` (`astromesh/tools/base.py`), hoy solo leído por `getattr`.

### 4. Inyección en retrieval (tocado: `AgentRunner.run`)
Paralelo exacto al bloque de memoria:
- Span `rag_build`.
- Si `self._rag`: `result = await self._rag.query(query_text)`; formatear
  `result.chunks` a texto; inyectar al render del prompt como una variable de contexto
  `knowledge` (junto a `memory`): `render(system_prompt, {..., "memory": ..., "knowledge": ...})`.
- Si `self._rag is None` o el KB no devuelve nada → `knowledge` vacío.

### 5. REST real (tocado: `astromesh/api/routes/rag.py`)
- `POST /rag/ingest {pipeline, document, metadata, doc_id_prefix}` → resolver `pipeline`
  del registro → `build_pipeline` → `await pipeline.ingest(...)` → `{"chunks": N}`.
- `POST /rag/query {pipeline, query, top_k}` → idem → `await pipeline.query(...)` →
  normalizar `RAGResult.chunks` → `{"results": [...], "query", "top_k"}`.
- Nota de reconciliación de contrato: `RAGPipeline.query()` devuelve un `RAGResult`
  (con `.chunks`), pero los tools existentes hacen `data={"results": results}` asumiendo
  una **lista**. Normalizar en un solo helper (`_result_to_list(RAGResult) -> list[dict]`)
  y usarlo tanto en el endpoint como en el tool wrapper, para que el shape de salida sea
  consistente (endpoint, tool e inyección always-on consumen lo mismo).

### 6. `rag.schema.json` (nuevo)
`vscode-extension/schemas/rag.schema.json`, paridad con `agent`/`workflow`:
- Schema de `kind: RAGPipeline` cubriendo `metadata` + `spec.{chunking,embeddings,
  vector_store,reranking,retrieval}`, con los enums de estrategias/providers/backends que
  el factory soporta (así el schema y el factory no divergen).
- Beneficio doble: validación en el loader y que Atlas (Slice 1) pueda validar su rag YAML
  contra un schema real en vez de no validarlo.

## Flujo de datos

**Ingesta (seed manual):**
```
POST /rag/ingest {pipeline: "product-knowledge", document, metadata}
  → resolver spec del registro → build_pipeline(spec)
  → pipeline.ingest(document, metadata): chunk → embed → upsert al store
  → {"chunks": N}
```

**Retrieval (runtime del agente):**
```
Agent con spec.knowledge.pipeline: product-knowledge  corre run(query)
  → self._rag.query(query): embed(query) → store.search(top_k) → [rerank]
  → chunks formateados → inyectados al system prompt como {"knowledge": ...}
  → el LLM responde fundamentado en el KB
```

## Contrato del bloque `spec.knowledge` (agente)

```yaml
spec:
  # ...identity, model, prompts, orchestration, memory...
  knowledge:
    pipeline: product-knowledge   # metadata.name de un kind: RAGPipeline
    top_k: 5                       # opcional; default = retrieval.top_k de la pipeline
```
Ausencia de `spec.knowledge` → el agente no tiene KB (`self._rag = None`), comportamiento
idéntico al actual.

## Manejo de errores — nunca romper la corrida

El KB es **aditivo, nunca un punto de falla** (mismo criterio no-fatal que la memoria):
- Nombre de pipeline no resuelto → warning + `self._rag = None`.
- Store vacío / sin resultados → `knowledge` vacío, el agente corre igual.
- Error del embedder o del store en `query()` → capturar, log, `knowledge` vacío, seguir.
- En `/rag/ingest` y `/rag/query` los errores sí se reportan al caller (son operaciones
  explícitas), con status/exception claros.

## Testing (`pytest` + `pytest-asyncio` + `ruff`, como el resto de astromesh)

Fakes deterministas (sin LLM/servicios): embedder de vector fijo + store in-memory (o
`FAISSStore`). Casos:
- **Loader**: parsea un `*.rag.yaml` válido a `RAGPipelineSpec`; rechaza `kind` incorrecto;
  saltea archivos inválidos.
- **Factory**: construye cada variante (`recursive`/`fixed`/…, `pgvector`/`faiss`/…) y
  levanta error claro ante un backend/strategy desconocido.
- **Resolución + inyección**: un agente con `spec.knowledge` recupera un chunk previamente
  ingestado y lo inyecta al prompt (assert sobre el contexto renderizado).
- **Degradación**: pipeline faltante / store vacío / embedder que tira → el `run()` no
  rompe y el `knowledge` queda vacío.
- **REST E2E**: `/rag/ingest` puebla y `/rag/query` recupera con fakes.
- **Tools reactivados**: con `ctx.rag_pipeline` seteado por la resolución, `rag_query`
  devuelve resultados con el shape normalizado (cubre el mismatch `RAGResult`→lista).
- Extender `tests/test_rag.py` / `tests/test_rag_tools.py` existentes donde aplique.

## Fuera de alcance (YAGNI — otras piezas del Slice 2 o posteriores)

- **Orquestación de ingesta**: fuentes (Drive/S3/web), sync incremental, re-index
  programado, watchers, gestión de colecciones.
- **`approval` (HITL) y `async` (pausa/resume durable)**: los otros dos capability-gaps
  del Slice 2, cada uno con su propio spec (async durable primero; approval depende de él).
- **Retrieval tool-based como camino primario**: queda disponible (tools activados) pero
  no se promueve por encima del always-on.
- **Ingesta/embeddings productivos gestionados** (colas, batching, costos): fuera.

## Follow-up en Clarus (tarea separada, NO en este spec)

En `clarus-platform`, el renderer de agentes de Atlas
(`apps/agents-clarus/.../atlas/render.py`) debería:
- Emitir `spec.knowledge.pipeline` en cada `Agent` que necesita KB, enlazándolo al
  `RAGPipeline` que ya genera (hoy emite la RAGPipeline suelta pero sin el enlace).
- Sumar `rag.schema.json` al contrato vendorizado (`astromesh_contract/`) y validar el rag
  YAML contra él en la fase `validate`.

## Criterios de aceptación

1. Un `*.rag.yaml` se carga al bootstrap y aparece en el registro por nombre.
2. `POST /rag/ingest` con un documento devuelve `chunks > 0` y persiste en el store.
3. Un agente con `spec.knowledge.pipeline` recupera e **inyecta** contexto del KB en su
   prompt, verificable en un test E2E con fakes.
4. Sin `spec.knowledge`, o ante KB vacío / errores de retrieval, el agente corre igual
   (ningún camino de RAG puede romper una corrida).
5. `rag_query` / `rag_ingest` devuelven resultados reales cuando el agente tiene pipeline.
6. `rag.schema.json` valida el ejemplo `config/rag/product-knowledge.rag.yaml`.
7. `pytest` verde y `ruff check` limpio.
