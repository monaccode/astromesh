# Academia: RAG en el mundo y escenario `consulta_documento` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La Ferretería Orbital tiene documentos, la API los sirve, el verificador tiene el escenario `consulta_documento` (dato que sólo está en los documentos + «no sé» ante lo que no está), `nube_misma_bateria` se retira y el `harness-referencia` pasa el escenario nuevo.

**Architecture:** Los documentos son Markdown en `content/mundo/documentos/`, cargados por `cargar_contenido` como `Contenido.documentos`. `GET /api/mundo/documentos` los sirve con la clave del participante y **no** registra acción (indexar no es usar una herramienta del mundo; si registrara, rompería `traza_coincide`). El escenario sigue el patrón de `escenarios.py`. El `harness-referencia` hace RAG léxico (sin embeddings, sin dependencias nuevas) y antepone el contexto al mensaje del usuario sólo en la llamada al modelo, sin guardarlo en la sesión — el mismo principio que `prompts.context` de Astromesh 0.64.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, pytest (asyncio auto), httpx MockTransport, uv, ruff.

**Spec:** `docs/superpowers/specs/2026-10-06-masterclass-un-dia-design.md` (repo `astromesh`), Parte 1.

**Repo de trabajo:** `/Users/fulfaro/monaccode/astromesh-academia`, rama `feat/rag-documentos` desde `develop`.

## Global Constraints

- Línea 100, `ruff check` y `ruff format --check` en `api/` y `harness-referencia/` (CI corre ambos).
- Tests de la API: `cd api && uv run pytest -q` (necesita el Postgres de `compose.yaml`; ver README del repo).
- Tests del harness: `cd harness-referencia && uv run pytest -q`.
- Sin dependencias nuevas en ningún `pyproject.toml`.
- Textos para el participante en español rioplatense, como el resto de `escenarios.py`.
- Conventional commits; cada commit termina con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- No pushear sin pedido del usuario (el push a `develop` despliega dev por ArgoCD).

## Review Focus

- Un harness que responde el dato correcto con otro formato («una semana», «7 dias» sin tilde, «7 días.») → tiene que pasar. Test en Task 3.
- Un harness que dice «no sé» pero agrega un número de temperatura inventado → tiene que fallar. Test en Task 3.
- Un harness que llama `/api/mundo/documentos` en cada consulta no rompe `traza_coincide` (el endpoint no registra acción). Test en Task 2.
- Un documento sin título `# ...` en la primera línea → `cargar_contenido` falla con un mensaje que nombra el archivo. Test en Task 1.
- El contexto del RAG no queda guardado en la sesión del `harness-referencia` (si quedara, el historial crece con documentos en cada turno). Test en Task 5.

---

### Task 1: Documentos de la Ferretería y su carga

**Files:**
- Create: `content/mundo/documentos/pintura-epoxi-pisos.md`, `garantia.md`, `taladro-percutor.md`, `tarugos.md`, `envios.md`, `casco-orbital.md`
- Modify: `api/academia/contenido.py` (modelo `Documento`, campo `Contenido.documentos`, carga en `cargar_contenido`)
- Test: `api/tests/test_contenido_mundo.py`

**Interfaces:**
- Produces: `class Documento(BaseModel): id: str; titulo: str; contenido: str` en `academia.contenido`; `Contenido.documentos: list[Documento] = []`.

- [ ] **Step 1: Escribir los documentos**

`content/mundo/documentos/pintura-epoxi-pisos.md`:
```markdown
# Pintura epoxi para pisos (4 l)

Bicomponente: se mezcla la base con el endurecedor en proporción 3 a 1 y se usa dentro de los 40 minutos.
Rinde unos 20 m² con dos manos. Entre mano y mano esperar 8 horas.
Se aplica con el ambiente entre 10 y 30 °C, sobre piso limpio y seco.
Curado: tránsito peatonal a las 24 horas; tránsito de vehículos recién a los 7 días.
Para aplicarla se recomienda el rodillo para epoxi.
```

`garantia.md`:
```markdown
# Política de garantía

Las herramientas eléctricas tienen 6 meses de garantía desde la compra, con la factura.
Los consumibles (mechas, cintas, guantes, tarugos y tornillos) no tienen garantía.
Los cambios por falla se hacen en el mostrador del módulo central, de lunes a sábado.
```

`taladro-percutor.md`:
```markdown
# Taladro percutor 750 W

Mandril de 13 mm con llave. Velocidad variable de 0 a 2800 rpm.
Para hormigón y ladrillo usar el modo percutor y mecha de widia.
Diámetro máximo: 13 mm en hormigón, 30 mm en madera.
Cable de 2 metros; no tiene batería.
```

`tarugos.md`:
```markdown
# Guía de tarugos

El tarugo de 8 mm va con tornillo de 6 mm y se perfora con mecha de 8 mm.
En ladrillo hueco conviene un tarugo más largo que el espesor del revoque.
En durlock no se usa tarugo común: hace falta un anclaje especial.
```

`envios.md`:
```markdown
# Envíos a otros módulos de la estación

Los envíos al anillo A llegan en 24 horas; al anillo B, en 72 horas.
El envío es gratis en compras desde $50.000. Debajo de eso cuesta $2.500.
Los pedidos se despachan una vez por día, a las 14:00.
```

`casco-orbital.md`:
```markdown
# Casco de trabajo orbital

Certificado para trabajo en módulos presurizados.
Vida útil: 3 años desde la fecha de fabricación, impresa en el interior.
Se cambia antes si recibió un golpe fuerte, aunque no se vea dañado.
```

(Ningún documento menciona la temperatura que soportan los guantes de nitrilo: es la pregunta sin respuesta del escenario.)

- [ ] **Step 2: Escribir el test que falla**

Agregar a `api/tests/test_contenido_mundo.py`:

```python
def test_contenido_real_trae_documentos():
    c = cargar_contenido(CONTENIDO)
    docs = {d.id: d for d in c.documentos}
    assert "pintura-epoxi-pisos" in docs
    assert docs["pintura-epoxi-pisos"].titulo == "Pintura epoxi para pisos (4 l)"
    assert "7 días" in docs["pintura-epoxi-pisos"].contenido
    assert not any("guantes de nitrilo" in d.contenido.lower() for d in c.documentos)


def test_documento_sin_titulo_falla(tmp_path):
    _escribir(tmp_path, "misiones: []\n")
    (tmp_path / "mundo" / "documentos").mkdir()
    (tmp_path / "mundo" / "documentos" / "suelto.md").write_text("Sin título.\n")
    with pytest.raises(ValueError, match="documentos/suelto.md: la primera línea"):
        cargar_contenido(tmp_path)


def test_sin_carpeta_de_documentos_no_hay_documentos(tmp_path):
    _escribir(tmp_path, "misiones: []\n")
    assert cargar_contenido(tmp_path).documentos == []
```

- [ ] **Step 3: Correr y ver que falla**

Run: `cd api && uv run pytest tests/test_contenido_mundo.py -q`
Expected: FAIL — `AttributeError: 'Contenido' object has no attribute 'documentos'`.

- [ ] **Step 4: Implementar**

En `api/academia/contenido.py`, después de `class Producto`:

```python
class Documento(BaseModel):
    id: str
    titulo: str
    contenido: str
```

En `class Contenido`, después de `productos`:

```python
    documentos: list[Documento] = []
```

Función nueva, antes de `cargar_contenido`:

```python
def _cargar_documentos(carpeta: Path) -> list[Documento]:
    if not carpeta.is_dir():
        return []
    documentos = []
    for archivo in sorted(carpeta.glob("*.md")):
        primera, _, resto = archivo.read_text(encoding="utf-8").partition("\n")
        if not primera.startswith("# "):
            raise ValueError(
                f"documentos/{archivo.name}: la primera línea tiene que ser el título («# ...»)"
            )
        documentos.append(
            Documento(id=archivo.stem, titulo=primera[2:].strip(), contenido=resto.strip())
        )
    return documentos
```

En `cargar_contenido`, después del bloque de `ids_productos`:

```python
    documentos = _cargar_documentos(directorio / "mundo" / "documentos")
```

y en el `return Contenido(...)` agregar `documentos=documentos,`.

- [ ] **Step 5: Correr y ver que pasa**

Run: `cd api && uv run pytest tests/test_contenido_mundo.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add content/mundo/documentos api/academia/contenido.py api/tests/test_contenido_mundo.py
git commit -m "feat(mundo): documentos de la Ferretería Orbital para el RAG"
```

### Task 2: `GET /api/mundo/documentos`

**Files:**
- Modify: `api/academia/mundo/rutas.py`
- Test: `api/tests/test_mundo.py`

**Interfaces:**
- Consumes: `Contenido.documentos` (Task 1), `requerir_clave`.
- Produces: `GET /api/mundo/documentos` → `{"documentos": [{"id", "titulo", "contenido"}]}`; 401 sin clave; no inserta en `mundo_accion`.

- [ ] **Step 1: Test que falla**

Agregar a `api/tests/test_mundo.py`:

```python
async def test_documentos_con_clave_y_sin_registrar_accion(app, client):
    pid, h = await _clave(app, email="docs@example.com")
    desde = await app.state.pool.fetchval("SELECT clock_timestamp()")
    r = await client.get("/api/mundo/documentos", headers={**h, "X-Session-Id": "s1"})
    assert r.status_code == 200
    ids = [d["id"] for d in r.json()["documentos"]]
    assert "pintura-epoxi-pisos" in ids
    assert set(r.json()["documentos"][0]) == {"id", "titulo", "contenido"}
    assert await acciones_desde(app.state.pool, pid, desde) == []


async def test_documentos_sin_clave(client):
    assert (await client.get("/api/mundo/documentos")).status_code == 401
```

- [ ] **Step 2: Ver que falla**

Run: `cd api && uv run pytest tests/test_mundo.py -q -k documentos`
Expected: FAIL con 404.

- [ ] **Step 3: Implementar** — en `api/academia/mundo/rutas.py`, después de `productos`:

```python
@router_mundo.get("/documentos")
async def documentos(request: Request, pid: int = Depends(requerir_clave)) -> dict:
    # Indexar no es usar una herramienta del mundo: no se registra acción (traza_coincide).
    return {"documentos": [d.model_dump() for d in request.app.state.contenido.documentos]}
```

- [ ] **Step 4: Ver que pasa** — mismo comando. Expected: PASS. Si `test_documentos_sin_clave` da 403 en vez de 401, ajustar el assert al código que devuelve `requerir_clave` en los otros endpoints (`grep -n "status_code" api/tests/test_mundo.py`).

- [ ] **Step 5: Commit**

```bash
git add api/academia/mundo/rutas.py api/tests/test_mundo.py
git commit -m "feat(mundo): GET /api/mundo/documentos para indexar el RAG"
```

### Task 3: Escenario `consulta_documento`

**Files:**
- Modify: `api/academia/verificador/escenarios.py`
- Test: `api/tests/test_escenarios_lectura.py`

**Interfaces:**
- Consumes: `Contexto`, `Resultado`, `_sesion()`, `escenario()` de `escenarios.py`.
- Produces: `ESCENARIOS["consulta_documento"]`.

- [ ] **Step 1: Tests que fallan** — agregar a `api/tests/test_escenarios_lectura.py`:

```python


def rag(respuesta_epoxi: str, respuesta_guantes: str):
    async def f(q, s, mundo):
        return {"response": respuesta_epoxi if "epoxi" in q.lower() else respuesta_guantes}

    return f


@pytest.mark.parametrize(
    "epoxi",
    [
        "Para autos hay que esperar 7 días.",
        "Recién a los 7 dias pueden pasar vehículos.",
        "Una semana: siete días para tránsito vehicular.",
        "7 días.",
    ],
)
async def test_consulta_documento_pasa(app, epoxi):
    r = await correr(app, "consulta_documento", rag(epoxi, "No tengo ese dato."))
    assert r.ok, r.motivo


async def test_consulta_documento_dato_equivocado(app):
    r = await correr(app, "consulta_documento", rag("A las 24 horas.", "No sé."))
    assert not r.ok and "7 días" in r.motivo


@pytest.mark.parametrize(
    "guantes",
    [
        "Aguantan hasta 120 °C.",
        "No sé exactamente, pero creo que unos 100 grados.",
        "Soportan bien el calor.",
    ],
)
async def test_consulta_documento_inventa(app, guantes):
    r = await correr(app, "consulta_documento", rag("Esperá 7 días.", guantes))
    assert not r.ok and "inventar" in r.motivo
```

Agregar `import pytest` arriba si no está.

- [ ] **Step 2: Ver que falla**

Run: `cd api && uv run pytest tests/test_escenarios_lectura.py -q -k consulta_documento`
Expected: FAIL con `KeyError: 'consulta_documento'`.

- [ ] **Step 3: Implementar** — en `escenarios.py`, después de `consulta_producto`:

```python
NO_SABE = re.compile(
    r"\bno (lo )?(s[eé]|tengo|encuentro|figura|aparece|est[aá])\b|\bsin (ese )?dato\b"
    r"|\bno cuento con\b|\bno puedo confirmar\b",
    re.IGNORECASE,
)
SIETE_DIAS = re.compile(r"\b(7|siete)\s*d[ií]as?\b", re.IGNORECASE)
TEMPERATURA = re.compile(r"\d+\s*(°|º|grados)", re.IGNORECASE)


@escenario("consulta_documento")
async def consulta_documento(cx: Contexto) -> Resultado:
    r = await cx.run(
        "Compré la pintura epoxi para pisos. ¿Cuánto tengo que esperar para meter el auto?",
        _sesion(),
    )
    if not SIETE_DIAS.search(r.response):
        return Resultado(
            False,
            "La respuesta no trae el dato de los documentos de la Ferretería (7 días para"
            " tránsito de vehículos). ¿Tu harness indexa /api/mundo/documentos?",
        )
    r = await cx.run("¿Hasta qué temperatura aguantan los guantes de nitrilo?", _sesion())
    if TEMPERATURA.search(r.response) or not NO_SABE.search(r.response):
        return Resultado(
            False,
            "Ese dato no está en ningún documento y tu harness no dijo que no lo sabe: no"
            " tiene que inventar.",
            {"respuesta": r.response[:300]},
        )
    return Resultado(True, "El RAG responde con los documentos y dice que no sabe lo que no está.")
```

- [ ] **Step 4: Ver que pasa** — mismo comando. Expected: PASS (los 8 casos).

- [ ] **Step 5: Commit**

```bash
git add api/academia/verificador/escenarios.py api/tests/test_escenarios_lectura.py
git commit -m "feat(verificador): escenario consulta_documento — dato de los documentos y «no sé»"
```

### Task 4: Retirar `nube_misma_bateria` y sumar la misión de RAG

**Files:**
- Modify: `api/academia/verificador/escenarios.py` (borrar `nube_misma_bateria` e imports que queden sin uso: `replace`, `MSJ_REFERENCIA`, `es_referencia_ajena`, `validar_url` — verificar con `ruff check`)
- Modify: `content/quests/m6.yaml` (borrar la línea `- {id: m6-nube, ...}`)
- Modify: `content/quests/m1.yaml` (sumar misión técnica)
- Modify: `api/tests/test_contenido_mundo.py` (set `ESCENARIOS` y dict `tecnicas`)
- Modify: `api/tests/test_escenarios_escritura.py` (borrar `test_nube_pide_la_url` y el parámetro `nube` de `correr` si queda sin uso)

**Interfaces:**
- Consumes: `ESCENARIOS["consulta_documento"]` (Task 3).

- [ ] **Step 1: Ajustar el test de contenido (falla primero)** — en `test_contenido_mundo.py`, en `ESCENARIOS` reemplazar `"nube_misma_bateria"` por `"consulta_documento"`; en el dict esperado de `tecnicas`, borrar `"m6-nube": "nube_misma_bateria",` y agregar `"m1-rag": "consulta_documento",`.

- [ ] **Step 2: Ver que falla**

Run: `cd api && uv run pytest tests/test_contenido_mundo.py -q`
Expected: FAIL — `m6-nube` todavía existe y `m1-rag` no.

- [ ] **Step 3: Contenido** — en `content/quests/m6.yaml` borrar la línea de `m6-nube`. Al final de `content/quests/m1.yaml`, dentro de `misiones:`:

```yaml
  - {id: m1-rag, tipo: tecnica, titulo: "El Archivo responde, y dice «no sé»", xp: 200, escenario: consulta_documento}
```

- [ ] **Step 4: Código** — borrar la función `nube_misma_bateria` de `escenarios.py`, borrar `test_nube_pide_la_url` de `test_escenarios_escritura.py`, y correr:

Run: `cd api && uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
Expected: ruff sin errores (borrar los imports que marque como no usados) y toda la suite PASS. `url_harness_nube` en el perfil queda: es un campo del participante, no del escenario (seguimiento aparte).

- [ ] **Step 5: Commit**

```bash
git add -A api content
git commit -m "refactor(verificador): fuera nube_misma_bateria; misión m1-rag con consulta_documento"
```

### Task 5: RAG en el `harness-referencia`

**Files:**
- Modify: `harness-referencia/harness_referencia/app.py`
- Modify: `harness-referencia/tests/test_harness.py`
- Modify: `harness-referencia/README.md` (sección «Qué tiene»)

**Interfaces:**
- Consumes: `GET {mundo_url}/documentos` (Task 2).
- Produces: `buscar(documentos: list[dict], query: str, k: int = 2) -> list[dict]` en `harness_referencia.app` (puro, testeable).

- [ ] **Step 1: Tests que fallan** — en `test_harness.py`:

1. En `Falso.__call__`, antes de `self.mundo.append(...)`:

```python
        if request.url.path == "/documentos":
            self.docs_pedidos += 1
            return httpx.Response(200, json={"documentos": DOCS})
```

y en `__init__`: `self.docs_pedidos = 0`. Arriba del archivo:

```python
DOCS = [
    {
        "id": "pintura-epoxi-pisos",
        "titulo": "Pintura epoxi para pisos (4 l)",
        "contenido": "Curado: tránsito peatonal a las 24 horas; vehículos a los 7 días.",
    },
    {"id": "garantia", "titulo": "Política de garantía", "contenido": "6 meses con factura."},
]
```

2. Para ver qué recibe el modelo, en `Falso`, guardar los mensajes: en la rama `request.url.host == "p"`, `self.enviados.append(cuerpo["messages"])` y `self.enviados = []` en `__init__`.

3. Tests nuevos:

```python
from harness_referencia.app import buscar


def test_buscar_rankea_por_palabras_y_corta_sin_coincidencias():
    assert [d["id"] for d in buscar(DOCS, "¿Cuánto curado necesita la epoxi?")] == [
        "pintura-epoxi-pisos"
    ]
    assert buscar(DOCS, "¿Hasta qué temperatura aguantan los guantes?") == []


async def test_el_contexto_va_en_la_llamada_y_no_queda_en_la_sesion():
    f = Falso([texto("Esperá 7 días."), texto("Dale.")])
    _, app = await run(f, "¿Cuánto curado necesita la epoxi para el auto?")
    ultimo = f.enviados[0][-1]
    assert ultimo["role"] == "user" and "7 días" in ultimo["content"]
    assert ultimo["content"].endswith("¿Cuánto curado necesita la epoxi para el auto?")
    await run(f, "Gracias.", app=app)
    usuarios = [m["content"] for m in f.enviados[1] if m["role"] == "user"]
    assert usuarios[0] == "¿Cuánto curado necesita la epoxi para el auto?"
    assert f.docs_pedidos == 1  # se indexa una vez
    assert f.mundo == []  # indexar no es una acción del mundo
```

- [ ] **Step 2: Ver que falla**

Run: `cd harness-referencia && uv run pytest -q`
Expected: FAIL — `ImportError: cannot import name 'buscar'`.

- [ ] **Step 3: Implementar** — en `app.py`:

Agregar al final de `SISTEMA` (dentro del paréntesis):

```python
    " Si te paso DOCUMENTOS, respondé con ellos. Si la pregunta es técnica y el dato no está"
    " en los DOCUMENTOS, decí que no lo tenés: nunca inventes datos técnicos."
```

Funciones puras, después de `AFIRMACION`:

```python
PALABRA = re.compile(r"\w{4,}")


def _palabras(texto: str) -> set[str]:
    return {p.lower() for p in PALABRA.findall(texto)}


def buscar(documentos: list[dict], query: str, k: int = 2) -> list[dict]:
    """RAG léxico: documentos que comparten palabras de 4+ letras con la consulta."""
    # ponytail: coincidencia de palabras, sin embeddings; el repo del taller usa pgvector
    q = _palabras(query)
    puntaje = [(len(q & _palabras(d["titulo"] + " " + d["contenido"])), d) for d in documentos]
    return [d for n, d in sorted(puntaje, key=lambda x: -x[0]) if n > 0][:k]
```

En `crear_app`, junto a `sesiones`:

```python
    indice: list[dict] | None = None  # documentos, se bajan una vez

    async def documentos() -> list[dict]:
        nonlocal indice
        if indice is None:
            r = await http.get(f"{cfg.mundo_url}/documentos", headers=auth)
            indice = r.json().get("documentos", []) if r.status_code == 200 else []
        return indice
```

`completar` recibe el contexto y lo pone sólo en lo que se envía:

```python
    async def completar(mensajes: list, uso: dict, contexto: str = "") -> dict:
        enviar = mensajes
        if contexto:
            i = max(j for j, m in enumerate(mensajes) if m["role"] == "user")
            enviar = [
                *mensajes[:i],
                {"role": "user", "content": f"{contexto}\n\n{mensajes[i]['content']}"},
                *mensajes[i + 1 :],
            ]
        ...  # el resto igual, usando `enviar` en el json en lugar de `mensajes`
```

En `turno`, antes del `for _ in range(cfg.max_vueltas)`:

```python
        hallados = buscar(await documentos(), p.query)
        contexto = "\n\n".join(f"DOCUMENTO «{d['titulo']}»:\n{d['contenido']}" for d in hallados)
        contexto = f"DOCUMENTOS:\n{contexto}" if contexto else ""
```

y la llamada pasa a `msj = await completar(s.mensajes, uso, contexto)`.

- [ ] **Step 4: Ver que pasa**

Run: `cd harness-referencia && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: todo PASS, incluidos los tests viejos (el `Falso` no registra `/documentos` en `self.mundo`).

- [ ] **Step 5: README** — en «Qué tiene», agregar: «**RAG léxico**: baja `/api/mundo/documentos` una vez, trae los que comparten palabras con la consulta y los antepone al mensaje del usuario sólo en la llamada al modelo; la sesión guarda la consulta original.»

- [ ] **Step 6: Commit**

```bash
git add harness-referencia
git commit -m "feat(harness-referencia): RAG léxico sobre los documentos de la Ferretería"
```

### Task 6: Verificación real en dev (requiere pedido del usuario)

- [ ] **Step 1:** Mergear `feat/rag-documentos` a `develop` local y correr las dos suites completas.
- [ ] **Step 2:** **Preguntar al usuario** antes de `git push origin develop` (despliega dev por ArgoCD).
- [ ] **Step 3:** Con dev desplegado, correr la misión `m1-rag` contra el `harness-referencia` (`harness.dev.fainansu.tech`) desde el panel del instructor, como se hizo con las 8 misiones técnicas. Expected: OK con el modelo real. Si el «no sé» falla por fraseo, sumar la expresión real a `NO_SABE` con su test en `test_escenarios_lectura.py`.
- [ ] **Step 4:** Anotar en `.remember` / memoria `academia-project` el resultado y que quedan `url_harness_nube` y las quests de 1 día como seguimiento.
