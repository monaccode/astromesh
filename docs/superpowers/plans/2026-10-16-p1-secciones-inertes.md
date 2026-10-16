# P1 — Secciones inertes, confirmación local en el ADK y `blocked` en Nexus — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que ninguna sección del manifiesto se acepte sin efecto: `permissions`, `memory.semantic/episodic`, `swarm` y `orchestration.timeout_seconds` pasan a funcionar; el ADK local aplica la compuerta de confirmación y `mode: propose`; Nexus persiste `blocked`/`guardrail`; Cortex, Forge, Leia y docs-site dejan de marcarlas como inertes.

**Architecture:** todo se cablea con piezas que ya existen — `fnmatch` sobre los nombres registrados en `ToolRegistry`, los backends de `astromesh/memory/backends/` construidos por `memory/factory.py` con import perezoso, el embedder de RAG, el `ciclo_de_tools` compartido por los patrones, `asyncio.timeout` alrededor de `pattern.execute`, y la compuerta de `runtime/confirmacion.py` reusada por el ADK. Nexus agrega dos columnas con el `ALTER TABLE` protegido por catálogo.

**Tech Stack:** Python 3.12 / pytest (asyncio auto) / ruff · Go (Nexus, gin, Postgres) · TypeScript + vitest (Cortex, Forge) · Markdown (Leia, docs-site Astro).

**Spec:** `docs/superpowers/specs/2026-10-16-p1-secciones-inertes-design.md` (vinculante). Hechos de base: `p1-facts.md` (resumido en la spec).

## Global Constraints

- Python 3.12; `uv run ruff check astromesh/ tests/` **y** `uv run ruff format --check astromesh/ tests/` antes de cada commit del core (CLAUDE.md: el gate de CI es el `--check`).
- CHANGELOG: todo commit `feat:`/`fix:`/`refactor:` lleva su entrada bajo `## [Unreleased]` en el mismo commit (core: `CHANGELOG.md`; ADK: `astromesh-adk/CHANGELOG.md`; Nexus/Cortex/Leia: el suyo).
- `python -c "import astromesh.api.main"` tiene que seguir funcionando **sin extras**: todo backend de memoria y embedder se importa dentro de la función que lo construye.
- Un manifiesto que hoy carga y deja de cargar lo hace con `AgentConfigError` cuyo mensaje dice qué cambiar.
- Un agente con `allowed_actions` que queda con cero tools habiendo declarado tools → warning fuerte (nivel ERROR), nunca silencio.
- El warning de caché por `memory.semantic/episodic` en `prompts.system` (`engine.py:1231-1237`) se mantiene.
- Trailer exacto en cada commit: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Prohibido `git stash`. Nexus, Cortex y Leia se trabajan en un worktree nuevo desde `origin/develop` (el checkout local puede estar viejo o sucio).
- Sin pasos de release/tag/bump de versión (van aparte: core 0.71.0, ADK 0.6.0, Nexus 0.26.13, Cortex 0.27.0, Forge 0.28.0, Leia 0.9.0).

## Review Focus

1. **`allowed_actions` escrito con el nombre del `spec.tools[]` de una integración** (`praxis`) cuando lo registrado es `praxis_crear_record`: el autor espera un aviso que le muestre los nombres reales, no un agente mudo. → Task 1 `test_patron_sin_match_avisa_con_los_nombres_registrados`.
2. **El modelo llama a una tool denegada que además tiene `confirm`** (o que inventó): no se ejecuta ni registra pendiente; `denied` gana antes de la compuerta. → Task 1 `test_tool_denegada_no_registra_pendiente`.
3. **El timeout vence después de que `tool_fn` registró un pendiente de confirmación**: el aviso nunca se mostró, así que un "si" en el turno siguiente no puede ejecutarlo. → Task 5 `test_timeout_cierra_el_pendiente_de_confirmacion`.
4. **Un `TimeoutError` que levanta una tool (no el plazo de la corrida)** no se puede reportar como `timeout`/504. → Task 5 `test_timeout_error_de_una_tool_no_es_timeout_de_corrida`.
5. **Episodios de otra sesión del mismo agente** (otra persona) llegando al prompt con su query. → Task 3 `test_episodios_de_otra_sesion_no_llegan_al_prompt`.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `astromesh/runtime/permisos.py` (nuevo) | Resolver `permissions` → set de nombres permitidos + avisos de carga |
| `astromesh/memory/factory.py` | + `build_semantic_memory`, `build_episodic_backend` (lazy) |
| `astromesh/core/memory.py` | Init perezoso, tolerancia a fallas, proyección al prompt, `record_run` |
| `astromesh/orchestration/patterns.py` | `ciclo_de_tools(..., finales=)` |
| `astromesh/orchestration/swarm.py` | Swarm sobre `ciclo_de_tools`, handoff = tool `type: agent`, `max_handoffs` |
| `astromesh/errors.py` | + `AgentRunTimeout` |
| `astromesh/runtime/confirmacion.py` | + `gate`, `aviso_confirmacion`, `con_aviso` (extraídos de `engine.py`) |
| `astromesh/runtime/engine.py` | Cableado de todo lo anterior |
| `astromesh/api/routes/agents.py` | 504 en timeout |
| `astromesh-adk/astromesh_adk/{runner,tools,result}.py` | Compuerta local + `mode="propose"` |

---

### Task 1: Core — `permissions.allowed_actions` / `denied_actions` aplicados

**Repo:** core · **Working dir:** `/Users/fulfaro/monaccode/astromesh-p1`

**Files:**
- Create: `astromesh/runtime/permisos.py`
- Modify: `astromesh/core/tools.py:55` (borrar `ToolDefinition.permissions`), `astromesh/core/tools.py:350-367` (`get_tool_schemas`)
- Modify: `astromesh/runtime/engine.py:1228-1230` (`_build_pattern` con schemas permitidos), `:1255-1258` (prefetch), `:1276` (`Agent(...)`), `:1564,1603` (`Agent.__init__`), `:1824` (schemas por corrida), `:2023` (`tool_fn`)
- Modify (sacar el mecanismo viejo / `permissions={}`): `tests/test_tools.py:70-92`, `tests/test_agent_as_tool.py:485-512`, `tests/test_glyph_pattern.py:120-130`, `tests/test_engine_role_routers.py:346`, `tests/test_rag_injection.py:53`, `tests/knowledge/test_okf_engine.py:108`
- Test: `tests/test_permisos.py`, `tests/test_permisos_engine.py`

**Interfaces:**
- Produces: `resolver_permisos(agent_name: str, registradas: Iterable[str], permissions: dict | None) -> frozenset[str] | None` — `None` = sin restricción (no hay `allowed_actions` ni `denied_actions`).
- Produces: `CLAVES_PERMISSIONS = frozenset({"allowed_actions", "denied_actions"})`.
- Produces: `ToolRegistry.get_tool_schemas(self, permitidas: Collection[str] | None = None) -> list[dict]`.
- Produces: `Agent.__init__(..., permitidas: frozenset[str] | None = None, ...)` reemplaza al parámetro `permissions`; `Agent._permitidas`.

- [ ] **Step 1: Tests unitarios del resolver** (`tests/test_permisos.py`)

```python
REG = ["praxis_crear_record", "praxis_leer_record", "kb_index", "kb_find", "lookup_company"]

def test_sin_permissions_no_restringe():
    assert resolver_permisos("a", REG, None) is None
    assert resolver_permisos("a", REG, {}) is None

def test_allowed_es_whitelist_con_comodines_fnmatch():
    r = resolver_permisos("a", REG, {"allowed_actions": ["praxis_*", "kb_index"]})
    assert r == {"praxis_crear_record", "praxis_leer_record", "kb_index"}

def test_denied_gana_sobre_allowed():
    r = resolver_permisos("a", REG, {"allowed_actions": ["praxis_*"],
                                     "denied_actions": ["praxis_crear_*"]})
    assert r == {"praxis_leer_record"}

def test_solo_denied_resta_de_todas():
    assert resolver_permisos("a", REG, {"denied_actions": ["kb_*"]}) == {
        "praxis_crear_record", "praxis_leer_record", "lookup_company"}

def test_match_es_case_sensitive():
    assert resolver_permisos("a", REG, {"allowed_actions": ["Praxis_*"]}) == frozenset()

def test_patron_sin_match_avisa_con_los_nombres_registrados(caplog):
    resolver_permisos("a", REG, {"allowed_actions": ["praxis", "lookup_company"]})
    msg = " ".join(r.getMessage() for r in caplog.records if r.levelname == "WARNING")
    assert "'praxis'" in msg and "praxis_crear_record" in msg

def test_cero_tools_es_aviso_fuerte(caplog):
    assert resolver_permisos("a", REG, {"allowed_actions": ["nada"]}) == frozenset()
    assert any(r.levelname == "ERROR" and "sin tools" in r.getMessage() for r in caplog.records)

def test_sin_tools_registradas_no_avisa_cero_tools(caplog):
    resolver_permisos("a", [], {"allowed_actions": ["x"]})
    assert not any(r.levelname == "ERROR" for r in caplog.records)

def test_clave_desconocida_se_reporta_como_ignorada(caplog):
    assert resolver_permisos("a", REG, {"filesystem": {"read": ["./"]}}) is None
    assert any("filesystem" in r.getMessage() and "no lee" in r.getMessage() for r in caplog.records)

@pytest.mark.parametrize("bad", [{"allowed_actions": "x"}, {"denied_actions": [1]}, ["x"]])
def test_tipo_invalido_es_error_de_config(bad):
    with pytest.raises(AgentConfigError, match="permissions"):
        resolver_permisos("a", REG, bad)
```

- [ ] **Step 2:** `uv run pytest tests/test_permisos.py -v` → FAIL (`ModuleNotFoundError: astromesh.runtime.permisos`).

- [ ] **Step 3: Implementar `astromesh/runtime/permisos.py`.** `fnmatch.fnmatchcase` (stdlib). Si `allowed_actions` está presente (aunque sea `[]`) es whitelist; `denied_actions` se resta después. Un warning por patrón (de cualquiera de las dos listas) que no matchea ninguna registrada, con la lista de registradas ordenada en el mensaje. Si `registradas` no está vacío y el resultado sí → `logger.error("agent %r: permissions deja al agente sin tools ...")`. Claves fuera de `CLAVES_PERMISSIONS` → un warning con el mismo texto que el de `claves_ignoradas` (`engine.py:976-983`: "… que este runtime no lee: %s. Se ignoran. …"). `permissions` que no es dict, o listas que no son `list[str]` → `AgentConfigError` cuyo mensaje nombra `permissions.<clave>` y dice "lista de nombres de tool (comodines fnmatch)".

- [ ] **Step 4:** `uv run pytest tests/test_permisos.py -v` → PASS.

- [ ] **Step 5: Tests de engine** (`tests/test_permisos_engine.py`). Agente con dos tools `type: client` (`leer`, `borrar`) armado con `AgentRuntime(config_dir="/nonexistent")._build_agent(spec)` (como `tests/test_client_tools.py:_agent_spec`) y `agent._routers["default"].route` falso (como `tests/test_guardrails_run.py:_agente`).

```python
async def test_tool_no_permitida_no_se_ofrece_al_modelo():
    # permissions: {allowed_actions: [leer]}
    # el route captura `tools` del request → nombres == ["leer"]

async def test_tool_no_permitida_que_el_modelo_llama_no_se_ejecuta():
    # el modelo emite tool_call "borrar" y después contesta
    # la observación del paso == {"error": "tool 'borrar' no permitida por permissions"}
    # (en el step, str() de ese dict); on_event no emite tool_call para "borrar"
    # el span "tool.call" de "borrar" tiene atributo "tool.denied" == True y status ERROR

async def test_tool_denegada_no_registra_pendiente():
    # tool integration con confirm + denied_actions: [<su nombre registrado>]
    # tras la corrida: _PENDIENTES.pendiente("s1") is None

def test_prefetch_de_tool_no_permitida_no_carga():
    # prefetch nombra "borrar", allowed_actions: [leer]
    # pytest.raises(AgentConfigError, match="prefetch.*borrar.*permissions")

def test_sin_permissions_se_ofrecen_todas():
    # get_tool_schemas(agent._permitidas) == las dos
```

- [ ] **Step 6:** `uv run pytest tests/test_permisos_engine.py -v` → FAIL.

- [ ] **Step 7: Cablear en el engine.** En `_build_agent`, después del repaso de `vigiladas` (`engine.py:1223-1227`): `permitidas = resolver_permisos(metadata["name"], tools._tools, spec.get("permissions"))`; `_build_pattern(spec, tools.get_tool_schemas(permitidas))`; después de `validar_prefetch` (`:1255`), si `permitidas is not None` y algún paso de prefetch nombra una tool fuera de `permitidas` → `AgentConfigError`. `Agent(..., permitidas=permitidas)`. En `Agent.run` `:1824`: `self._tools.get_tool_schemas(self._permitidas)`. En `tool_fn` (`:2023`), **antes** del bloque de confirmación: si `self._permitidas is not None and name not in self._permitidas` → span `tool.call` con `{"tool": name, "tool.denied": True}`, `finish_span(..., SpanStatus.ERROR)`, devolver `{"error": f"tool '{name}' no permitida por permissions"}` sin `_emit`. `get_tool_schemas`: `if permitidas is not None and name not in permitidas: continue`. Borrar `ToolDefinition.permissions` y los tests del filtro viejo listados arriba; sacar `permissions={}` de los `Agent(...)` a mano.

- [ ] **Step 8:** `uv run pytest tests/ -q -x` → PASS (toda la suite: `Agent(...)` cambió de firma).

- [ ] **Step 9: CHANGELOG** — `### Added (Backend)`: "`permissions.allowed_actions`/`denied_actions` restringen de verdad: whitelist de nombres **registrados** con comodines `fnmatch`, `denied` gana, se aplica al ofrecer y al ejecutar". Ruff check + format --check.

- [ ] **Step 10: Commit**

```bash
git -C /Users/fulfaro/monaccode/astromesh-p1 add astromesh/runtime/permisos.py astromesh/core/tools.py astromesh/runtime/engine.py tests/ CHANGELOG.md
git -C /Users/fulfaro/monaccode/astromesh-p1 commit -m "feat(permissions): allowed_actions/denied_actions aplicados al ofrecer y al ejecutar tools

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Core — memoria semántica y episódica construidas desde el manifiesto

**Repo:** core · **Working dir:** `/Users/fulfaro/monaccode/astromesh-p1`

**Files:**
- Modify: `astromesh/memory/factory.py`
- Modify: `astromesh/rag/factory.py:41,113` (`_build_embedder` → `build_embedder`, público; actualizar su único llamador)
- Modify: `astromesh/core/memory.py:79-207` (`MemoryManager`)
- Modify: `astromesh/runtime/engine.py:907-914` (construcción del `MemoryManager`)
- Test: `tests/test_memory_factory.py`, `tests/test_memoria_semantica_engine.py` (nuevo)

**Forma del manifiesto (vinculante para Tasks 6, 10, 11, 12, 13):**

```yaml
memory:
  semantic:
    backend: chromadb | faiss | pgvector | qdrant     # requerido
    similarity_threshold: 0.75                        # default 0.75 (ya lo lee build_context)
    max_results: 10                                   # default 10
    embeddings: {provider: ollama | hf | sentence_transformer, model: ..., endpoint: ..., api_key: ...}  # requerido
    path: ./data/chroma          # sólo chromadb; sin path = cliente en memoria
    connection: {url: ...}       # requerido en pgvector; opcional en qdrant (sin url = :memory:)
    dimension: 768               # requerido en faiss, pgvector, qdrant
  episodic:
    backend: postgres            # único válido
    connection: {url: postgresql://...}   # requerido
```

**Interfaces:**
- Produces: `build_semantic_memory(cfg: dict | None) -> tuple[SemanticBackend, Callable[[str], Awaitable[list[float]]]] | None` (backend + `embedding_fn`).
- Produces: `build_episodic_backend(cfg: dict | None) -> EpisodicBackend | None`.
- Produces: `build_embedder(cfg: dict) -> EmbeddingProvider` en `astromesh/rag/factory.py`.
- Produces: `MemoryManager._preparar() -> None` (async; `initialize()` una vez en los backends que lo tienen).

- [ ] **Step 1: Tests del factory** (agregar a `tests/test_memory_factory.py`)

```python
def test_semantic_ausente_es_none():
    assert build_semantic_memory(None) is None and build_episodic_backend({}) is None

def test_semantic_backend_desconocido_nombra_los_validos():
    with pytest.raises(AgentConfigError, match="chromadb, faiss, pgvector, qdrant"):
        build_semantic_memory({"backend": "in_memory", "embeddings": {"provider": "ollama"}})

def test_semantic_sin_embeddings_es_error():
    with pytest.raises(AgentConfigError, match="embeddings"):
        build_semantic_memory({"backend": "chromadb"})

@pytest.mark.parametrize("backend", ["faiss", "pgvector", "qdrant"])
def test_dimension_requerida(backend):
    with pytest.raises(AgentConfigError, match="dimension"):
        build_semantic_memory({"backend": backend, "embeddings": {"provider": "ollama"},
                               "connection": {"url": "postgresql://x"}})

@pytest.mark.parametrize("modulo,backend,extra", [
    ("chromadb", "chromadb", "chromadb"), ("faiss", "faiss", "faiss"),
    ("qdrant_client", "qdrant", "qdrant"), ("asyncpg", "pgvector", "postgres")])
def test_falta_el_extra_nombra_el_extra(monkeypatch, modulo, backend, extra):
    monkeypatch.setitem(sys.modules, modulo, None)
    # sacar también el módulo del backend ya importado, si lo estaba
    with pytest.raises(AgentConfigError, match=rf"astromesh\[{extra}\]"):
        build_semantic_memory({"backend": backend, "dimension": 8,
                               "connection": {"url": "postgresql://x"},
                               "embeddings": {"provider": "ollama"}})

def test_sentence_transformer_sin_extra_es_error(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda n, *a: None if n == "sentence_transformers" else ...)
    with pytest.raises(AgentConfigError, match=r"astromesh\[embeddings\]"): ...

def test_episodic_solo_postgres_con_url():
    with pytest.raises(AgentConfigError, match="postgres"):
        build_episodic_backend({"backend": "redis"})
    with pytest.raises(AgentConfigError, match="connection.url"):
        build_episodic_backend({"backend": "postgres"})

def test_api_main_importa_sin_extras():
    code = ("import sys\n"
            "for m in ('chromadb','faiss','qdrant_client','asyncpg','sentence_transformers'):"
            " sys.modules[m] = None\n"
            "import astromesh.api.main")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env={**os.environ, "ASTROMESH_SKIP_RUNTIME": "1"})
    assert r.returncode == 0, r.stderr
```

- [ ] **Step 2:** `uv run pytest tests/test_memory_factory.py -v` → FAIL (`ImportError: build_semantic_memory`).

- [ ] **Step 3: Implementar en `memory/factory.py`.** Cada backend se importa dentro de su rama; `ImportError` → `AgentConfigError(f"memory.semantic.backend {b!r} necesita el extra: pip install 'astromesh[{extra}]'")` con el mapa `{chromadb: chromadb, faiss: faiss, qdrant: qdrant, pgvector: postgres}` (episódica: `postgres`). Embedder: `from astromesh.rag.factory import build_embedder` adentro; para `sentence_transformer`, `importlib.util.find_spec("sentence_transformers") is None` → error con `astromesh[embeddings]`. `embedding_fn = embedder.embed`. Constructores: `ChromaSemanticBackend(path=cfg.get("path"))`, `FAISSSemanticBackend(dimension=)`, `PGVectorSemanticBackend(dsn=url, dimension=)`, `QdrantSemanticBackend(url=, dimension=)`, `PGEpisodicBackend(dsn=url)`.

- [ ] **Step 4:** `uv run pytest tests/test_memory_factory.py -v` → PASS.

- [ ] **Step 5: Tests del `MemoryManager` cableado** (`tests/test_memoria_semantica_engine.py`; `monkeypatch` de `astromesh.runtime.engine.build_semantic_memory` para devolver un `FakeSemantic` + `embed` falso)

```python
async def test_el_manifiesto_construye_la_semantica(tmp_path, monkeypatch):
    # memory: {semantic: {backend: faiss, dimension: 3, embeddings: {provider: ollama}}}
    assert agente._memory._semantic is fake and agente._memory._embed is not None

def test_semantic_sin_embeddings_deja_el_agente_en_draft(tmp_path):
    # bootstrap real: runtime._agent_status["g-agent"] == "draft"
    # "embeddings" in runtime.agent_error("g-agent")

async def test_backend_que_falla_en_search_no_rompe_la_corrida(caplog):
    # FakeSemantic.search levanta RuntimeError → run devuelve answer, warning logueado

async def test_backend_que_falla_en_store_no_rompe_la_corrida(): ...

async def test_semantica_se_escribe_sin_memoria_conversacional():
    # sin memory.conversational, respuesta del asistente > 50 tokens → FakeSemantic.stored tiene 1

async def test_initialize_se_llama_una_vez():
    # FakeSemantic con initialize() contador; dos corridas → 1
```

- [ ] **Step 6:** FAIL. **Step 7: Implementar.** Engine `:907`: `sem = build_semantic_memory(memory_spec.get("semantic"))`; `MemoryManager(..., semantic=sem[0] if sem else None, embedding_fn=sem[1] if sem else None, episodic=build_episodic_backend(memory_spec.get("episodic")))` — `import` de las funciones arriba del módulo (el factory no importa extras a nivel módulo). `AgentConfigError` sube → el agente queda en `draft` con el mensaje (`bootstrap` ya lo hace, `engine.py:534-544`). En `MemoryManager`: `_preparar()` al principio de `build_context` y `persist_turn` (flag por instancia; si `initialize()` falla se loguea y se reintenta en la próxima llamada); `try/except Exception` + `logger.warning(..., exc_info=True)` alrededor de la búsqueda semántica, el `recall` episódico y el `store` semántico; `turn.token_count` se calcula antes del `if self._conversation` (hoy la escritura semántica depende de que haya conversacional).

- [ ] **Step 8:** `uv run pytest tests/test_memory_factory.py tests/test_memoria_semantica_engine.py tests/test_memory.py tests/test_memory_backends.py -v` → PASS; `uv run pytest tests/ -q` → PASS.

- [ ] **Step 9:** CHANGELOG `### Added (Backend)`: memoria semántica/episódica desde el manifiesto, `embeddings` obligatorio, extras por backend. Ruff. **Commit** `feat(memory): memory.semantic y memory.episodic se construyen desde el manifiesto` + trailer.

---

### Task 3: Core — episodio por corrida y proyección segura al prompt

**Repo:** core · **Working dir:** `/Users/fulfaro/monaccode/astromesh-p1`

**Files:**
- Modify: `astromesh/core/memory.py` (`build_context`, nuevo `record_run`)
- Modify: `astromesh/runtime/engine.py` (`Agent.run`: acumular tools/tokens, escribir episodio en `:2248` ok, `:2262` bloqueo, `:2290` error)
- Test: `tests/test_memoria_episodica_engine.py` (nuevo)

**Interfaces:**
- Consumes: `MemoryManager(semantic=, episodic=, embedding_fn=)` de Task 2.
- Produces: `MemoryManager.record_run(self, session_id: str, *, query: str | None, resultado: Literal["ok", "blocked", "error", "timeout"], tools: list[str], tokens: dict[str, int], regla: str | None = None) -> None` — nunca levanta; no-op sin backend episódico. Episodio: `EpisodicMemory(event_type="run", summary=(query or "")[:500], context={"session_id": session_id, "tools": tools}, outcome={"result": resultado, "tokens": tokens, "guardrail": regla}, timestamp=datetime.now(UTC))`.
- Produces: `build_context` devuelve `context["semantic"]` como `list[{"content", "similarity", "source"}]` y `context["episodic"]` como `list[{"event_type", "summary", "context", "outcome", "timestamp"}]` (`timestamp` en ISO), sólo episodios con `context.session_id == session_id`, los 5 más recientes (de un `recall(limit=50)`).
- Produces (para Task 5): dentro de `Agent.run`, `async def _episodio(resultado: str, regla: str | None = None, con_query: bool = True) -> None`.

- [ ] **Step 1: Tests** (`FakeEpisodic` con `record` → lista y `recall` → lo grabado; helper como `tests/test_guardrails_run.py:_agente`)

```python
async def test_una_corrida_ok_deja_un_episodio():
    # una tool client "leer" llamada y respuesta final; usage output_tokens=7
    ep = fake.grabados[0]
    assert ep.event_type == "run" and ep.outcome["result"] == "ok"
    assert ep.context["tools"] == ["leer"] and ep.outcome["tokens"] == {"input": 6, "output": 7}
    assert ep.summary == "hola"

async def test_query_larga_se_trunca_a_500(): assert len(ep.summary) == 500

async def test_bloqueo_de_entrada_deja_episodio_sin_query():
    # guardrails: {input: [{type: topic_filter, blocked_topics: [secreto], action: block}]}
    assert ep.outcome["result"] == "blocked" and ep.outcome["guardrail"] == "topic_filter"
    assert ep.summary == "" and "secreto" not in json.dumps(dataclasses.asdict(ep), default=str)

async def test_bloqueo_de_salida_guarda_la_query(): assert ep.summary == "<query filtrada>"

async def test_error_deja_episodio_error():
    # route levanta RuntimeError → pytest.raises; fake.grabados[0].outcome["result"] == "error"

async def test_fallo_al_grabar_el_episodio_no_rompe_la_corrida():
    # FakeEpisodic.record levanta → result["answer"] == "ok"

async def test_proyeccion_semantica_sin_vector():
    # prompts.context: "{{ memory.semantic | tojson }}"; FakeSemantic devuelve SemanticMemory(embedding=[0.1]*3)
    # en el mensaje enviado al modelo: '"content"' presente, '0.1' ausente;
    # agente._memory.build_context(...)["semantic"][0].keys() == {"content", "similarity", "source"}

async def test_episodios_de_otra_sesion_no_llegan_al_prompt():
    # corrida en "s1" con query "dato-de-s1"; corrida en "s2" → "dato-de-s1" no aparece en lo enviado al modelo
```

- [ ] **Step 2:** FAIL. **Step 3: Implementar.** En `Agent.run`: `tools_llamadas: list[str] = []` (append en `tool_fn` justo antes de `self._tools.execute`, sólo si se ejecuta) y `uso = {"input": 0, "output": 0}` (sumado donde `model_fn` ya lee `response.usage`, `engine.py:1954`). `_episodio(...)` llama `self._memory.record_run(session_id, query=query_text if con_query else None, ...)`. Puntos: después de `_persistir_turno` (ok); en `except GuardrailBlocked` con `con_query=bloqueo.direction != "input"`, `regla=bloqueo.rule`; en `except Exception` con `"error"` (envuelto en `contextlib.suppress(Exception)` para no tapar el error original).

- [ ] **Step 4:** `uv run pytest tests/test_memoria_episodica_engine.py -v` → PASS; suite completa → PASS.

- [ ] **Step 5:** CHANGELOG `### Added (Backend)`: episodio por corrida (`ok|blocked|error|timeout`, tools, tokens, regla; sin query si se bloqueó la entrada), proyección `{content, similarity, source}` sin vector, episodios de la misma sesión. Ruff. **Commit** `feat(memory): un episodio por corrida y memoria proyectada al prompt sin vectores` + trailer.

---

### Task 4: Core — `swarm` con handoff real

**Repo:** core (+ `astromesh-adk` para no romper su `_run_swarm`) · **Working dir:** `/Users/fulfaro/monaccode/astromesh-p1`

**Files:**
- Modify: `astromesh/orchestration/patterns.py:65` (`ciclo_de_tools`)
- Rewrite: `astromesh/orchestration/swarm.py`
- Modify: `astromesh/core/tools.py:224-262` (rama AGENT: propagar el contador)
- Modify: `astromesh/runtime/engine.py:1366-1389` (`_build_pattern`), `:2128` (contexto del patrón)
- Modify: `astromesh-adk/astromesh_adk/runner.py:606-625` (`_run_swarm`), `astromesh-adk/astromesh_adk/team.py:66-71` (borrar `_build_agent_configs`) y `astromesh-adk/tests/test_team.py:86-96`
- Test: `tests/test_swarm_agents.py` (reescribir), `tests/test_swarm_engine.py` (nuevo), `astromesh-adk/tests/test_runner_local.py`

**Interfaces:**
- Produces: `ciclo_de_tools(messages, model_fn, tool_fn, tools, max_iterations, role, permitidas=None, presupuesto=None, finales: Collection[str] | None = None) -> dict` — si el modelo llama una tool en `finales`, su resultado es la respuesta: devuelve `{"answer": obs["answer"] if dict con "answer" else str(obs), "steps": steps, "final_agent": name}` sin volver al modelo.
- Produces: `SwarmPattern(workers: list[str], max_handoffs: int = 3)`, `consumes_turn_context = True`; constante `CLAVE_HANDOFFS = "_handoffs"` en `swarm.py`.
- Produces: el contexto que `Agent.run` pasa al patrón lleva `CLAVE_HANDOFFS: int((context or {}).get(CLAVE_HANDOFFS, 0))`.

- [ ] **Step 1: Tests del patrón** (`tests/test_swarm_agents.py`, `model_fn`/`tool_fn` `AsyncMock`)

```python
async def test_handoff_devuelve_la_respuesta_del_destino_como_final():
    # model_fn → tool_call "especialista" {"query": "revisá esto"}; tool_fn → {"answer": "listo"}
    r = await SwarmPattern(workers=["especialista"]).execute("q", {}, model_fn, tool_fn, TOOLS)
    assert r["answer"] == "listo" and r["final_agent"] == "especialista"
    assert model_fn.await_count == 1

async def test_el_destino_recibe_la_historia():
    ctx = {"_history_messages": [{"role": "user", "content": "hola"},
                                 {"role": "assistant", "content": "¿qué necesitás?"}]}
    args = tool_fn.await_args.args[1]
    assert "hola" in args["query"] and "¿qué necesitás?" in args["query"] and "revisá esto" in args["query"]

async def test_handoff_incrementa_el_contador():
    # context {} → args["_handoffs"] == 1 ; context {"_handoffs": 2} → 3

async def test_tope_de_handoffs_no_ofrece_agentes_ni_los_ejecuta():
    # context {"_handoffs": 3}, max_handoffs=3: nombres en tools de model_fn no incluyen "especialista";
    # si igual lo llama, tool_fn no se llama con "especialista"

async def test_tool_comun_es_observacion_no_final():
    # tool_call "leer" → tool_fn("leer", ...) y el modelo vuelve a ser llamado; answer = segunda respuesta

async def test_sin_handoff_contesta_directo(): ...

async def test_no_agrega_un_system_propio():
    # ningún mensaje con role "system" en lo que recibe model_fn
```

- [ ] **Step 2:** FAIL. **Step 3: Implementar.** `ciclo_de_tools`: tras `tool_fn` de una tool en `finales`, `return` inmediato (las demás tool_calls de esa respuesta no se ejecutan). `SwarmPattern.execute`: `n = context.get(CLAVE_HANDOFFS, 0)`; si `n >= max_handoffs` se quitan los workers de `tools` y de `permitidas`; envuelve `tool_fn` para que una llamada a worker vaya con `{**args, "query": <transcripción de _history_messages + "Pedido: " + args["query"]>, CLAVE_HANDOFFS: n + 1}`; llama `ciclo_de_tools(mensajes_de_conversacion(query, context), ..., role="reasoner", presupuesto=presupuesto_de(context), finales=workers_activos)`. Rama AGENT de `ToolRegistry.execute`: si `CLAVE_HANDOFFS in arguments`, `transform_ctx = {**(transform_ctx or {}), CLAVE_HANDOFFS: arguments[CLAVE_HANDOFFS]}`. Engine: en el `context=` de `pattern.execute` agregar `CLAVE_HANDOFFS`.

- [ ] **Step 4: Tests de engine** (`tests/test_swarm_engine.py`)

```python
def test_swarm_sin_tools_agent_no_carga():
    with pytest.raises(AgentConfigError, match="type: agent"): ...

@pytest.mark.parametrize("v", [0, -1, "3", True])
def test_max_handoffs_invalido_no_carga(v):
    with pytest.raises(AgentConfigError, match="max_handoffs"): ...

def test_max_handoffs_default_3():
    assert agent._pattern._max_handoffs == 3

async def test_handoff_real_corre_el_otro_agente(tmp_path):
    # dos YAML en config/agents: "triage" (swarm, tool type: agent → "billing") y "billing" (react)
    # route de triage → tool_call "billing"; route de billing → "soy billing"
    r = await runtime.run("triage", "quiero mi factura", "s1")
    assert r["answer"] == "soy billing"
```

- [ ] **Step 5: Implementar `_build_pattern`** para `swarm`: workers = nombres de tools `type: agent` (mismo código que supervisor, `engine.py:1366-1376`); vacío → `AgentConfigError("`pattern: swarm` necesita al menos una tool `type: agent`: son los agentes a los que puede pasar el control")`; `orchestration.max_handoffs` entero ≥ 1, no bool, default 3, si no `AgentConfigError` que nombre `max_handoffs`.

- [ ] **Step 6: ADK.** `_run_swarm`: `SwarmPattern(workers=list(agents))`, specs `self._adk_tools_to_specs([a.as_tool() for a in team.agents])`, `handoff_tool_fn` devuelve `{"answer": r.answer}` y corre al miembro con `args["query"]`. Borrar `AgentTeam._build_agent_configs` y `test_team_build_agent_configs`. Test nuevo en `astromesh-adk/tests/test_runner_local.py`:

```python
async def test_run_team_swarm_handoff_answer_is_final():
    # entry agent emite tool_call al miembro "writer"; writer contesta "draft"
    assert result.answer == "draft"
```

- [ ] **Step 7:** `uv run pytest tests/test_swarm_agents.py tests/test_swarm_engine.py tests/test_supervisor_agents.py -v` → PASS; `uv run pytest tests/ -q` → PASS; `cd astromesh-adk && uv run pytest -q` → PASS.

- [ ] **Step 8:** CHANGELOG core `### Changed`: swarm = handoff real a tools `type: agent`, la respuesta del destino es la final, `orchestration.max_handoffs` (default 3), ahora con historial, `prompts.context` como mensaje y tope de resultados de tools. ADK `CHANGELOG.md` `[Unreleased] ### Changed`: equipos `swarm` con handoff por tool call. Ruff (core y `astromesh-adk`). **Commit** `feat(swarm): handoff real entre agentes con max_handoffs` + trailer.

---

### Task 5: Core — `orchestration.timeout_seconds` corta la corrida

**Repo:** core · **Working dir:** `/Users/fulfaro/monaccode/astromesh-p1`

**Files:**
- Modify: `astromesh/errors.py` (+ `AgentRunTimeout`)
- Modify: `astromesh/runtime/engine.py` (`_build_agent` validación; `Agent.__init__` `_timeout_seconds`; `Agent.run` alrededor de `:2128` + nueva rama `except AgentRunTimeout`)
- Modify: `astromesh/api/routes/agents.py:333-338`
- Test: `tests/test_timeout_engine.py` (nuevo), `tests/test_api_timeout.py` (nuevo)

**Interfaces:**
- Consumes: `_episodio(...)` de Task 3; `_PENDIENTES` (`engine.py:56`).
- Produces: `class AgentRunTimeout(TimeoutError)` con `__init__(self, agent: str, timeout_seconds: float)` y esos dos atributos.
- Produces: `Agent(..., timeout_seconds: float | None = None)`.

- [ ] **Step 1: Tests** (patrones falsos como `_PideLaTool` de `tests/test_confirmacion_engine.py:76`)

```python
async def test_sin_timeout_no_corta(): # patrón que duerme 0.05 s, sin la clave → answer

async def test_timeout_corta_la_corrida():
    # timeout_seconds: 0.05, patrón duerme 5 s
    with pytest.raises(AgentRunTimeout) as e: await agente.run("q", "s1")
    assert e.value.timeout_seconds == 0.05 and time.monotonic() - t0 < 1

@pytest.mark.parametrize("v", [0, -5, "60", True])
def test_timeout_invalido_no_carga(v):
    with pytest.raises(AgentConfigError, match="timeout_seconds"): ...

def test_alias_timeout_aplica_y_avisa(caplog):
    # orchestration: {timeout: 30} → agent._timeout_seconds == 30; warning menciona "timeout_seconds"

async def test_timeout_error_de_una_tool_no_es_timeout_de_corrida():
    # patrón que levanta TimeoutError propio, timeout_seconds: 60
    with pytest.raises(TimeoutError) as e: ...
    assert not isinstance(e.value, AgentRunTimeout)

async def test_timeout_cierra_el_pendiente_de_confirmacion():
    # patrón: _PENDIENTES.registrar("s1", "t", "fp", {}) y duerme → AgentRunTimeout
    assert _PENDIENTES.pendiente("s1") is None

async def test_timeout_deja_episodio_timeout():
    # FakeEpisodic de Task 3 → outcome["result"] == "timeout"; root span con "timeout" == True
```

`tests/test_api_timeout.py`:

```python
async def test_run_timeout_devuelve_504(client, monkeypatch):
    # monkeypatch del runtime: run levanta AgentRunTimeout("a", 60)
    resp = await client.post("/v1/agents/a/run", json={"query": "q", "session_id": "s"})
    assert resp.status_code == 504
    assert resp.json()["detail"] == {"error": "timeout", "agent": "a", "timeout_seconds": 60}
```

- [ ] **Step 2:** FAIL. **Step 3: Implementar.** `_build_agent`: `timeout_seconds` (o el alias `timeout`, con warning de deprecación) tiene que ser `int|float` > 0 y no bool, si no `AgentConfigError`. En `Agent.run`, `async with asyncio.timeout(self._timeout_seconds) as plazo:` alrededor de `self._pattern.execute(...)` (con `None` no corta); `except TimeoutError: if plazo.expired(): raise AgentRunTimeout(self.name, self._timeout_seconds) from None; raise` — `asyncio.timeout` en lugar de `wait_for` porque `expired()` distingue el plazo propio del `TimeoutError` de una tool (misma semántica que pide la spec). Rama nueva `except AgentRunTimeout:` antes de `except Exception`: si `desde_humano` y hay pendiente con `ok=False` → `_PENDIENTES.cerrar(session_id)`; `root_span.set_attribute("timeout", True)`; `_episodio("timeout")`; `finish_span(root_span, SpanStatus.ERROR)`; re-raise. No se persiste el turno. Ruta: `except AgentRunTimeout as e: raise HTTPException(504, detail={"error": "timeout", "agent": e.agent, "timeout_seconds": e.timeout_seconds})` antes de `except ValueError`.

- [ ] **Step 4:** `uv run pytest tests/test_timeout_engine.py tests/test_api_timeout.py -v` → PASS; suite → PASS (si un test existente arma un agente con `timeout_seconds` chico y patrón lento, subir el valor en el test).

- [ ] **Step 5:** CHANGELOG `### Changed`: `timeout_seconds` corta la corrida → `AgentRunTimeout` / HTTP 504 `{"error": "timeout", ...}`; `timeout` es alias deprecado. Ruff. **Commit** `feat(orchestration): timeout_seconds corta la corrida con 504` + trailer.

---

### Task 6: Core — manifiestos/templates del repo, schema del editor y nota "Breaking"

**Repo:** core · **Working dir:** `/Users/fulfaro/monaccode/astromesh-p1`

**Files:**
- Modify: `config/agents/sales-qualifier.agent.yaml` (`allowed_actions: [lookup_company]`; quitar `memory.semantic`, no hay embedder garantizado donde bootea el API)
- Modify: `config/agents/whatsapp-assistant.agent.yaml` (quitar `permissions`: no tiene tools)
- Modify: `config/agents/astromesh-copilot.agent.yaml:55-62` (quitar `permissions.filesystem/network/execution`: no los lee nadie)
- Modify: `config/templates/brand-chef.template.yaml:92`, `config/templates/support-agent.template.yaml:86` (agregar `embeddings: {provider: ollama, model: nomic-embed-text}`)
- Modify: `timeout_seconds` de los 20 manifiestos listados por `grep -rn timeout_seconds config/agents config/templates` → `120` donde sea menor (no tocar `config/workflows/`)
- Modify: `vscode-extension/schemas/agent.schema.json` (`permissions.denied_actions`, `semantic.backend` enum `chromadb|faiss|pgvector|qdrant` + `embeddings`/`path`/`connection`/`dimension`, `episodic` `{backend: postgres, connection}`, `orchestration.max_handoffs`, descripciones sin "inert")
- Modify: `CHANGELOG.md` (bloque **Breaking for existing manifests** al tope de `[Unreleased]`)
- Test: `tests/test_manifest_secciones.py` (nuevo)

**Interfaces:**
- Consumes: forma del manifiesto de Task 2; `resolver_permisos` de Task 1.

- [ ] **Step 1: Test** (mismo `ARCHIVOS` y recorrido que `tests/test_manifest_guardrails.py`)

```python
@pytest.mark.parametrize("archivo", ARCHIVOS, ids=lambda p: p.name)
def test_secciones_del_manifiesto_tienen_efecto(archivo):
    spec = _spec(yaml.safe_load(archivo.read_text()))
    perms = spec.get("permissions") or {}
    assert set(perms) <= {"allowed_actions", "denied_actions"}
    nombres = [t["name"] for t in spec.get("tools", [])]
    for p in perms.get("allowed_actions", []):
        assert any(fnmatch.fnmatchcase(n, p) or n.startswith(p.rstrip("*")) for n in nombres), p
    sem = (spec.get("memory") or {}).get("semantic")
    assert sem is None or "embeddings" in sem
    t = (spec.get("orchestration") or {}).get("timeout_seconds")
    assert t is None or t >= 120
```

- [ ] **Step 2:** FAIL → **Step 3:** editar manifiestos/templates/schema → **Step 4:** `uv run pytest tests/test_manifest_secciones.py tests/test_manifest_guardrails.py tests/test_api_templates.py tests/test_engine.py -v` → PASS.

- [ ] **Step 5: CHANGELOG** — al tope de `[Unreleased]`, con el formato de la de 0.70.0 (`CHANGELOG.md:76`):

```
**Breaking for existing manifests.** Secciones que se aceptaban sin efecto ahora hacen algo:
- `orchestration.timeout_seconds` corta la corrida (HTTP 504, `error: "timeout"`). Valores de
  30–90 s cortan corridas con tools o modelos lentos; el timeout HTTP del provider es 120 s.
  Recomendado: ≥ 120 o quitar la clave.
- `permissions.allowed_actions` es una whitelist de nombres registrados (`<slug>_<acción>` en
  integration/api/mcp, `kb_*` en bundles); un nombre que no matchea deja esa tool afuera.
- `memory.semantic` sin `embeddings` no carga (`AgentConfigError`); cada backend pide su extra.
- `pattern: swarm` sin tools `type: agent` no carga.
- `permissions.filesystem/network/execution` y otras claves se ignoran con warning.
```

Ruff. **Commit** `fix(config): manifiestos y templates del repo al día con las secciones aplicadas` + trailer.

---

### Task 7: Core — extraer la compuerta de confirmación a `runtime/confirmacion.py`

**Repo:** core · **Working dir:** `/Users/fulfaro/monaccode/astromesh-p1`

**Files:**
- Modify: `astromesh/runtime/confirmacion.py` (+ funciones)
- Modify: `astromesh/runtime/engine.py:243-284` (`_aviso_confirmacion` pasa a ser alias), `:2025-2063` (bloque de `tool_fn`), `:2236-2246` (aviso)
- Modify: `astromesh/integrations/propuestas.py:52` (`tipo: Literal["api", "mcp", "adk"]`)
- Test: `tests/test_confirmacion.py` (+ unitarios); red existente: `tests/test_confirmacion_engine.py`, `tests/test_patrones_confirmacion_engine.py`

**Interfaces:**
- Produces: `gate(pendientes: Pendientes, session_id: str, tool_name: str, args: dict) -> dict | None` — `None` = puede ejecutarse (y ya consumió la licencia con `cerrar`); si no, registra y devuelve el dict `{"error": "confirmacion_requerida", "pendiente": {"tool", "argumentos"}, "mensaje": <texto actual, copiado literal de engine.py:2049-2055>}`.
- Produces: `aviso_confirmacion(tool_name: str, argumentos: dict) -> str` (cuerpo y docstring movidos; helper privado de truncado con la misma salida que `engine._truncate`).
- Produces: `con_aviso(pendientes: Pendientes, session_id: str, answer: object) -> str` — agrega el aviso si hay pendiente con `ok=False`; si no, devuelve `answer` como str.
- `engine._aviso_confirmacion` y `engine._PENDIENTES` siguen importables (los tests los usan).

- [ ] **Step 1: Tests unitarios** (`tests/test_confirmacion.py`)

```python
def test_gate_sin_confirmacion_registra_y_devuelve_el_pendiente():
    p = Pendientes(); r = gate(p, "s", "t", {"a": 1})
    assert r["error"] == "confirmacion_requerida" and r["pendiente"] == {"tool": "t", "argumentos": {"a": 1}}

def test_gate_confirmado_deja_pasar_una_sola_vez():
    p = Pendientes(); gate(p, "s", "t", {"a": 1}); p.habilitar("s", "si")
    assert gate(p, "s", "t", {"a": 1}) is None
    assert gate(p, "s", "t", {"a": 1})["error"] == "confirmacion_requerida"

def test_con_aviso_agrega_el_texto_del_runtime():
    p = Pendientes(); gate(p, "s", "t", {"a": 1})
    assert con_aviso(p, "s", "hecho").endswith("Para confirmar respondé SI. Voy a ejecutar: t con a: 1")
    assert con_aviso(Pendientes(), "s", "hecho") == "hecho"
```

- [ ] **Step 2:** FAIL → **Step 3:** mover código; engine llama `gate(_PENDIENTES, session_id, name, args)` y `result["answer"] = con_aviso(_PENDIENTES, session_id, result.get("answer"))` dentro del `if desde_humano`. Sin cambio de comportamiento.
- [ ] **Step 4:** `uv run pytest tests/test_confirmacion.py tests/test_confirmacion_engine.py tests/test_patrones_confirmacion_engine.py -v` → PASS sin tocar los tests de engine; suite → PASS.
- [ ] **Step 5:** CHANGELOG `### Changed`: "la compuerta de confirmación vive en `runtime/confirmacion.py` (`gate`, `aviso_confirmacion`, `con_aviso`) para reusarla desde el ADK; sin cambio de comportamiento". Ruff. **Commit** `refactor(confirmacion): compuerta reutilizable fuera de engine.py` + trailer.

---

### Task 8: ADK — compuerta local (`requires_approval`) y `mode="propose"`

**Repo:** core monorepo, paquete `astromesh-adk` · **Working dir:** `/Users/fulfaro/monaccode/astromesh-p1/astromesh-adk`

**Files:**
- Modify: `astromesh_adk/tools.py:89-158` (`ToolDefinitionWrapper`, `tool()`: kwarg `mode`)
- Modify: `astromesh_adk/runner.py:106-113` (`ADKRuntime.__init__`: `self._pendientes = Pendientes()`), `:197-232` (`_make_tool_fn`), `:342-419` (`run_agent`), `:501-504,585-625` (miembros con `desde_humano=False`)
- Modify: `astromesh_adk/result.py:26` (docstring: local y remoto)
- Modify: `README.md` (sección "Confirmación y propuestas en local")
- Test: `tests/test_runner_confirmacion.py` (nuevo)

**Interfaces:**
- Consumes: `gate`, `con_aviso`, `Pendientes`, `huella` (Task 7); `handler_de_propuesta(tool, tipo="adk", destino=<agent name>, operacion=<tool name>, schema=<parameters_schema>)`, `CLAVE_PROPUESTAS`, `SOLO_PRINCIPAL` (`astromesh/integrations/propuestas.py`).
- Produces: `tool(description, ..., requires_approval: bool = False, mode: Literal["execute", "propose"] = "execute")`; `ToolDefinitionWrapper.mode`; `mode` inválido → `ValueError`.
- Produces: `ADKRuntime.run_agent(..., callbacks=None, desde_humano: bool = True) -> RunResult` con `RunResult.propuestas` llenado en local.

- [ ] **Step 1: Tests** (helpers de `tests/test_runner_local.py`: provider falso que emite tool_calls)

```python
async def test_requires_approval_no_ejecuta_la_primera_vez():
    # @tool(requires_approval=True) async def pagar(monto: int); el modelo la llama
    assert ejecutadas == [] and "Voy a ejecutar: pagar con monto: 10" in r.answer

async def test_confirmar_re_corriendo_con_si_ejecuta_una_vez():
    await a.run("pagá 10", session_id="s"); await a.run("si", session_id="s")   # modelo repite la llamada
    assert ejecutadas == [10]

async def test_confirmar_con_otros_argumentos_no_ejecuta(): ...

async def test_un_miembro_de_equipo_no_autoconfirma():
    # supervisor delega con query "si" a un worker con tool requires_approval → no ejecuta

async def test_mode_propose_no_ejecuta_y_devuelve_la_propuesta():
    # @tool(mode="propose") async def crear(nombre: str)
    assert ejecutadas == [] and r.propuestas[0]["tool"] == "crear"
    assert r.propuestas[0]["argumentos"] == {"nombre": "x"} and r.propuestas[0]["tipo"] == "adk"

async def test_mode_propose_en_miembro_de_equipo_no_registra():
    # worker con tool propose → observación con SOLO_PRINCIPAL, r.propuestas == []

def test_mode_invalido_es_error():
    with pytest.raises(ValueError, match="mode"): tool("d", mode="dry")(f)
```

- [ ] **Step 2:** `uv run pytest tests/test_runner_confirmacion.py -v` → FAIL.
- [ ] **Step 3: Implementar.** `run_agent`: `if desde_humano: self._pendientes.habilitar(session_id, query)` antes de los guardrails de entrada (texto crudo, como el core); `propuestas = [] if desde_humano else SOLO_PRINCIPAL`; `tool_fn` (con `agent_name`, `session_id`, `propuestas` en la clausura): si `getattr(t, "requires_approval", False)` → `if (r := gate(self._pendientes, session_id, name, args)) is not None: return r`; si `getattr(t, "mode", "execute") == "propose"` → `return await handler_de_propuesta(...)(_run_context={CLAVE_PROPUESTAS: propuestas}, **args)` sin llamar la función. Tras el patrón y los guardrails de salida: `if desde_humano: answer = con_aviso(self._pendientes, session_id, answer)`; en `GuardrailBlocked` cerrar el pendiente `ok=False` (como `engine.py:2256-2262`); `finally: if desde_humano: self._pendientes.cerrar_si_confirmado(session_id)`; `RunResult.from_runtime({..., "propuestas": propuestas if isinstance(propuestas, list) else []})`. `_run_member`, `delegating_tool_fn`, `handoff_tool_fn` → `desde_humano=False`.
- [ ] **Step 4:** `uv run pytest -q` (en `astromesh-adk`) → PASS; `uv run ruff check . && uv run ruff format --check .` → limpio.
- [ ] **Step 5:** `astromesh-adk/CHANGELOG.md` `[Unreleased] ### Added`: compuerta local, `mode="propose"`, confirmar = re-correr con "si" en la misma sesión. El piso `astromesh>=0.71.0` + `uv lock` **no** va acá: el path source sigue en 0.70.0 hasta el release del core (si se sube antes, `uv lock` no resuelve). **Commit** `feat(adk): confirmación local con requires_approval y mode="propose"` + trailer.

---

### Task 9: Nexus — `blocked` y `guardrail` persistidos en `invocations`

**Repo:** astromesh-nexus · **Working dir:** `git -C /Users/fulfaro/monaccode/astromesh-nexus fetch origin && git -C /Users/fulfaro/monaccode/astromesh-nexus worktree add /Users/fulfaro/monaccode/astromesh-nexus-p1 -b feat/p1-blocked origin/develop` → trabajar en `/Users/fulfaro/monaccode/astromesh-nexus-p1`

**Files:**
- Modify: `internal/store/postgres.go:~783` (dos bloques `DO $$ … IF NOT EXISTS (pg_attribute …) THEN ALTER TABLE invocations ADD COLUMN … END $$` después del de `session_id`)
- Modify: `internal/store/invocations.go:59-87` (`Invocation` + `Blocked bool`, `Guardrail json.RawMessage`), `:441-461` (`InvocationOutcome` + los mismos), `:345,363` (SELECT), `:413-433` (`scanInvocation`), `:469-500` (UPDATE de `CloseInvocation`: `blocked = $13, guardrail = $14`)
- Modify: `internal/store/observability.go:264`, `internal/store/platform.go:~495` (SELECT con `i.blocked, i.guardrail`)
- Modify: `internal/server/handlers/invocations.go:~426` y `invocations_stream.go:~124` (`Blocked: res.Blocked, Guardrail: res.Guardrail` en el outcome `ok`)
- Modify: `internal/server/handlers/observability.go:90-121` (`clientInvocation`: `Blocked bool \`json:"Blocked,omitempty"\``, `Guardrail json.RawMessage \`json:"Guardrail,omitempty"\``; `toClientInvocation` los copia)
- Modify: `CHANGELOG.md` (`## [Unreleased]`)
- Test: `internal/store/postgres_test.go`, `internal/server/handlers/invocations_propuestas_test.go`, `internal/server/handlers/observability_test.go`

**Interfaces:**
- Consumes: `runtime.RunResult.Blocked/Guardrail` (`internal/runtime/client.go:120-121`, ya parseados).
- Produces: columnas `blocked boolean not null default false`, `guardrail jsonb null`; JSON de cliente `Blocked`/`Guardrail` (PascalCase como el resto de `clientInvocation`), ausentes cuando no hubo bloqueo.

- [ ] **Step 1: Tests**

```go
// postgres_test.go (con TEST_DATABASE_URL, como los existentes)
func TestCloseInvocationPersistsBlockedAndGuardrail(t *testing.T)
//   Close con Blocked: true, Guardrail: `{"direction":"input","rule":"topic_filter","reason":"x"}`
//   GetInvocation → inv.Blocked == true; JSONEq(inv.Guardrail, ...)
func TestCloseInvocationNotBlockedLeavesGuardrailNull(t *testing.T)
//   inv.Blocked == false && inv.Guardrail == nil
// Los existentes TestPostgresStoreSecondBootCompletesWhileInvocationsIsBeingWritten y
// TestMigrationCreatesBillingSchema/second_migrate...issues_no_DDL tienen que seguir verdes.

// invocations_propuestas_test.go (fake store)
func TestRunAndStreamRecordGuardrailBlock(t *testing.T)
//   runtime falso devuelve Blocked → el outcome que recibe CloseInvocation tiene Blocked && Guardrail, en /run y /run/stream

// observability_test.go
func TestInvocationDetailAndLogsCarryBlock(t *testing.T)
//   GET …/invocations/:id y /logs: "Blocked": true y "Guardrail" presentes
func TestInvocationJSONOmitsBlockWhenNotBlocked(t *testing.T)
//   las claves "Blocked" y "Guardrail" no aparecen
```

- [ ] **Step 2:** `go test ./internal/... -run 'Blocked|Block' -v` → FAIL. **Step 3:** implementar según Files. **Step 4:** `go test ./...` (con `TEST_DATABASE_URL` si está disponible; si no, los de store se saltean: decirlo) y `go vet ./...` → PASS.
- [ ] **Step 5:** CHANGELOG `### Added`: columnas, `CloseInvocation` las escribe, detalle y `/logs` las exponen (aditivo). **Commit** en el worktree: `feat(invocations): persistir blocked y guardrail de la corrida` + trailer.

---

### Task 10: Cortex — schema e inspectores sin marcas de inerte

**Repo:** astromesh-cortex · **Working dir:** `git -C /Users/fulfaro/monaccode/astromesh-cortex worktree add /Users/fulfaro/monaccode/astromesh-cortex-p1 -b feat/p1-secciones origin/develop` → `/Users/fulfaro/monaccode/astromesh-cortex-p1` (`npm ci`)

**Files:**
- Modify: `src/schemas/agent.schema.json` (`permissions`: `allowed_actions`/`denied_actions` arrays de string, descripción con fnmatch; `memory.semantic`: enum `chromadb|faiss|pgvector|qdrant`, `embeddings` `{provider enum ollama|hf|sentence_transformer, model, endpoint, api_key}`, `path`, `connection.url`, `dimension`; `episodic`: `{backend: enum [postgres], connection: {url}}`; `orchestration.timeout_seconds` sin "inert"; `orchestration.max_handoffs` integer ≥1)
- Create: `src/components/visual-agent/inspectors/tool-names.ts` — `registeredToolNames(spec): string[]`
- Modify: `src/components/visual-agent/inspectors/PermissionsInspector.tsx` (dos listas de patrones con `<datalist>` alimentado por `registeredToolNames`)
- Modify: `src/components/visual-agent/inspectors/MemoryInspector.tsx:70` (editor de semantic + embeddings y episodic)
- Modify: `src/components/visual-agent/inspectors/OrchestrationInspector.tsx:13,67` (swarm sin "Not wired"; campo `timeout_seconds`; campo `max_handoffs` si `pattern === 'swarm'`; aviso rojo si swarm sin tools `type: agent`, como supervisor)
- Modify: `src/schemas/__tests__/fixtures/core/*.agent.yaml` (re-copiar de `astromesh-p1/config/agents/` tras Task 6)
- Modify: `CHANGELOG.md`
- Test: `src/components/visual-agent/inspectors/__tests__/{PermissionsInspector,MemoryInspector,OrchestrationInspector}.test.tsx`, `src/components/visual-agent/inspectors/__tests__/tool-names.test.ts`

**Interfaces:**
- Consumes: forma del manifiesto de Task 2; nombres registrados del core (`<slug>_<acción>` con `-`→`_`, `kb_index|kb_read|kb_find`).
- Produces: `registeredToolNames(spec)` = nombres de tools `builtin|agent|client` + `"<name con - → _>_*"` para `integration|api|mcp` + `kb_*` si `spec.knowledge.bundle`.

- [ ] **Step 1: Tests (vitest)**

```ts
it('registeredToolNames sugiere comodín para tools derivadas y kb_*', () => {
  expect(registeredToolNames({ tools: [{ name: 'leer', type: 'client' }, { name: 'mi-api', type: 'api' }],
    knowledge: { bundle: 'b' } })).toEqual(['leer', 'mi_api_*', 'kb_*'])
})
it('PermissionsInspector escribe allowed_actions y denied_actions como listas', ...)   // updateSection('permissions', {allowed_actions: ['leer'], denied_actions: ['mi_api_*']})
it('PermissionsInspector no muestra la marca de inerte', ...)                          // queryByText(/no aplica/) === null
it('MemoryInspector escribe semantic con embeddings y no inventa claves vacías', ...)
it('OrchestrationInspector edita timeout_seconds y max_handoffs (swarm)', ...)
it('swarm sin tools type: agent muestra el aviso', ...)
it('el schema valida las fixtures del core', ...)   // test existente, verde con las fixtures nuevas
```

- [ ] **Step 2:** `npx vitest run src/components/visual-agent` → FAIL. **Step 3:** implementar. **Step 4:** `npm test && npm run lint && npx tsc --noEmit` → PASS.
- [ ] **Step 5:** CHANGELOG `[Unreleased] ### Changed`. **Commit** `feat(editor): permissions, memoria semántica/episódica, swarm y timeout_seconds editables` + trailer.

---

### Task 11: Forge — round-trip y wizard sin marcas de inerte

**Repo:** core monorepo, `astromesh-forge` · **Working dir:** `/Users/fulfaro/monaccode/astromesh-p1/astromesh-forge`

**Files:**
- Modify: `src/types/agent.ts:109-136` (`permissions.denied_actions?: string[]`; `orchestration.max_handoffs?: number`; quitar `filesystem/network/execution`)
- Modify: `src/components/wizard/StepSettings.tsx:203-210` (reemplazar "Core 0.70 does not use it" por un resumen: backend + embeddings; si falta `embeddings`, aviso "el runtime no carga el agente sin embeddings")
- Modify: `src/components/wizard/StepOrchestration.tsx:38-41` (swarm: "Hands control to a `type: agent` tool; its answer is final") y campo `max_handoffs` cuando `pattern === "swarm"`
- Modify: `src/data/pipeline-presets.ts:6` (comentario)
- Modify: `CHANGELOG.md` del core, `### Changed (Astromesh Forge)`
- Test: `src/utils/__tests__/core070-roundtrip.test.ts` → renombrar a `core071-roundtrip.test.ts` y extender

- [ ] **Step 1: Test**

```ts
it("round-trip keeps permissions, semantic+embeddings, episodic, swarm+max_handoffs and timeout_seconds", () => {
  // manifiesto con permissions {allowed_actions: ["kb_*"], denied_actions: ["kb_read"]},
  // memory.semantic {backend: faiss, dimension: 768, embeddings: {provider: ollama, model: nomic-embed-text}},
  // memory.episodic {backend: postgres, connection: {url: "postgresql://x"}},
  // orchestration {pattern: swarm, max_handoffs: 2, timeout_seconds: 120}
  expect(nodesToAgent(agentToNodes(cfg)).spec).toEqual(cfg.spec)
})
```

- [ ] **Step 2:** `npx vitest run src/utils` → FAIL (o PASS si el round-trip ya lo conserva: entonces el test queda como red y el cambio es de UI/tipos). **Step 3:** implementar. **Step 4:** `npm test && npm run lint && npm run build` → PASS.
- [ ] **Step 5: Commit** `feat(forge): secciones aplicadas por core 0.71 sin marcas de inerte` + trailer.

---

### Task 12: Leia — schemas y arquitecto al día

**Repo:** astromesh-leia · **Working dir:** `git -C /Users/fulfaro/monaccode/astromesh-leia worktree add /Users/fulfaro/monaccode/astromesh-leia-p1 -b feat/p1-secciones origin/develop` → `/Users/fulfaro/monaccode/astromesh-leia-p1`

**Files:**
- Modify: `schemas/astromesh-v1-agent.md` (`:312` `timeout_seconds` aplicado + 504; `:868-890` semantic/episodic con la forma de Task 2; `:1023` permissions con fnmatch/denied/nombres registrados; `:1178` lista de "deliberately absent"; `:283-285` swarm ya separa `prompts.context`)
- Modify: `schemas/orchestration-patterns.md` (`:5,18,33,55-56` swarm real, `max_handoffs`)
- Modify: `agents/leia-architect.md:50,141,171,173` (puede emitir swarm/permissions/memoria/timeout; `timeout_seconds` ≥ 120 recomendado)
- Modify: `commands/logs.md` y `schemas/nexus-api.md:~941` (`Blocked`/`Guardrail` en detalle y `/logs`; `/leia logs` marca la fila bloqueada con su regla)
- Modify: `CHANGELOG.md`

- [ ] **Step 1:** `git grep -n -i "inert\|not read\|never built\|not enforced\|0\.68\|0\.70" -- schemas agents commands` → lista de líneas a corregir (las que hablan de estas cuatro secciones).
- [ ] **Step 2:** editar. **Step 3:** el mismo grep no devuelve ninguna línea sobre `permissions`, `semantic`, `episodic`, `swarm` ni `timeout_seconds`; versión de core citada = 0.71.0.
- [ ] **Step 4: Commit** `docs: schemas y arquitecto con permissions, memoria, swarm y timeout aplicados` + trailer.

---

### Task 13: docs-site — documentar el comportamiento

**Repo:** core monorepo, `docs-site` · **Working dir:** `/Users/fulfaro/monaccode/astromesh-p1/docs-site`

**Files:**
- Modify: `src/content/docs/configuration/agent-yaml.md` (`:122,349` timeout corta → 504; `:173,442-443` memoria semántica/episódica con forma, extras y episodio; `:193,503` permissions; `:374` swarm sí tiene tope de resultados; `:514` swarm; `:496` agregar párrafo "Before 0.71.0 …" con la lista Breaking de Task 6)
- Modify: `src/content/docs/configuration/multi-agent.md:8,374-400` (swarm real: tools `type: agent`, respuesta final, historial, `max_handoffs`)
- Modify: `src/content/docs/reference/core/tool-registry.md:243-256`
- Modify: `src/content/docs/adk/creating-tools.mdx:110` (`requires_approval` y `mode="propose"` aplicados en local; confirmar = `await agent.run("si", session_id=...)`), `src/content/docs/adk/multi-agent.mdx:50`
- Modify: `src/content/docs/leia/introduction.mdx:96` (fila de Leia 0.9.0)

- [ ] **Step 1:** `grep -rn -i "not enforced\|not read\|inert\|does not invoke\|not built\|no se aplica" src/content/docs` → lista de líneas sobre estas secciones.
- [ ] **Step 2:** editar (en inglés, como el sitio). **Step 3:** `npm run build` → PASS; el grep del Step 1 ya no devuelve líneas sobre permissions, memoria semántica/episódica, swarm, `timeout_seconds` ni `requires_approval`.
- [ ] **Step 4:** CHANGELOG del core `### Changed (Docs)`. **Commit** `docs(site): permissions, memoria, swarm, timeout y confirmación local documentados` + trailer.

---

## Orden y dependencias

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 en el worktree del core (3 usa a 2; 5 usa `_episodio` de 3; 6 asume 1–5; 8 usa 7). 9 es independiente; 12 usa los nombres de JSON de 9. 10, 11 y 13 van después de 6 (forma final del manifiesto y fixtures).

## Self-review (hecho)

- Cobertura: objetivos 1→T1, 2→T2+T3, 3→T4, 4→T5, 5→T7+T8, 6→T9, 7→T10–T13; anti-objetivos: carga con mensaje (T1/T2/T4/T5 `AgentConfigError`), `api.main` sin extras (T2 `test_api_main_importa_sin_extras`), cero tools (T1), warning de caché intacto (no se toca `engine.py:1231`).
- Tipos consistentes: `resolver_permisos`/`_permitidas`, `build_semantic_memory`/`build_episodic_backend`, `record_run`/`_episodio`, `SwarmPattern(workers, max_handoffs)`/`CLAVE_HANDOFFS`, `AgentRunTimeout(agent, timeout_seconds)`, `gate`/`con_aviso`/`aviso_confirmacion`.
