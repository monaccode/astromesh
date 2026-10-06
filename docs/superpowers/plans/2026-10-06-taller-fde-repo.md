# Repo `astromesh-taller-fde` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un repo público, en Python, que el alumno clona el día del curso: arranca como un esqueleto que responde `POST /run` y, estación por estación (8 tags `estacion-N`), se convierte en un harness con loop, tools, router, RAG en pgvector, contexto por niveles con presupuesto y resumen, compuertas, trazas OTLP y costo. Todo corre en Docker igual en Linux, Mac y Windows.

**Architecture:** Un paquete `harness/` cuyo centro es `Harness.turno(query, session_id) -> dict`. Cada dependencia es opcional y «apagada» por defecto (sin `indice` no hay RAG, sin `ventana` no hay recorte, sin `techo` no hay techo, `prefetch: false`), así los tests de una estación siguen pasando cuando se suman las siguientes. `app.py` es una capa HTTP fina sobre una función `turno`. Los tests usan un modelo falso guionado y un mundo falso; desde Archivo, también el Postgres del compose. Cada estación es: commit de esqueleto (README + tests en rojo + stubs con `NotImplementedError`, sin cablear) → tag `estacion-N` → commit de solución.

**Tech Stack:** Python 3.12, uv, FastAPI, httpx, PyYAML, asyncpg + pgvector (Archivo), Ollama `nomic-embed-text` (Archivo), OpenTelemetry SDK + OTLP HTTP + Jaeger (Torre), pytest + pytest-asyncio, ruff, Docker Compose v2, cloudflared, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-06-masterclass-un-dia-design.md` (repo `astromesh`), Parte 2. Diseño publicado: https://claude.ai/artifact/TjyDB3sFV5ikkhej2sLHk1

**Depende de:** `docs/superpowers/plans/2026-10-06-academia-rag.md` (endpoint `/api/mundo/documentos` y escenario `consulta_documento`) para verificar Archivo contra la Academia real. El código y los tests de este repo no dependen de él.

**Directorio de trabajo:** `/Users/fulfaro/monaccode/astromesh-taller-fde` (nuevo; `git init -b main`).

## Global Constraints

- Público. Licencia: MIT para el código (`LICENSE`), CC BY 4.0 para los textos de `estaciones/*/README.md` (`LICENSE-textos`).
- Python ≥ 3.12, `uv`, línea 100, `ruff check` y `ruff format --check` limpios en cada commit de solución.
- En la máquina del alumno sólo Docker, git y el agente de código. **Nada de `Makefile` ni scripts de shell en el host**: los comandos del curso corren en el servicio `taller` (`python -m taller`).
- `.gitattributes` con `* text=auto eol=lf`. Skills como copias, no symlinks.
- Imágenes multi-arquitectura (amd64 y arm64).
- Chat: Kimi por la pasarela de la Academia (`{ACADEMIA_URL}/api/pasarela/v1`, OpenAI-compatible) con `ACADEMIA_CLAVE` (se entrega en el Muelle). Candidatos: `kimi-k2.6` → `kimi-k2.7-code-highspeed`. No mandar `temperature` (kimi-k2.6 sólo admite 1 con thinking activo).
- Embeddings: Ollama `nomic-embed-text` (768 dimensiones), desde Archivo. No hay modelo de chat local.
- Contrato `POST /run`: entrada `{"query", "session_id"}`; salida `{"response", "usage": {"input_tokens", "output_tokens", ...}, "trace": [{"tool", "args"}]}`; 502 con `{"error"}` si ningún modelo responde, sin tocar la sesión.
- `trace` lista sólo las herramientas ejecutadas de verdad contra el mundo (una escritura frenada por la compuerta no aparece). Indexar documentos no es una herramienta.
- Tests sin red y sin costo: modelo falso, mundo falso, embedder falso; Postgres del compose desde Archivo.
- Conventional commits; cada commit termina con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Crear el repo en GitHub y pushear sólo en la Task 11 (nombre y licencia ya aprobados por el usuario: `monaccode/astromesh-taller-fde`, público, MIT + CC BY 4.0). Pushear los tags **de a uno** (más de 3 tags en un push no dispara workflows).

## Review Focus

- La pasarela devuelve 429 por techo de gasto del alumno → el harness no tiene que tratarlo como «modelo no disponible» y saltar al respaldo (cuesta lo mismo y también da 429): tiene que devolver 502 con el mensaje. Test en Task 4.
- Un turno que falla a mitad del loop (el modelo responde y en la segunda vuelta ningún candidato responde) → la sesión queda como estaba antes del turno. Test en Task 3.
- El recorte del historial nunca deja un mensaje `tool` sin su `assistant` con `tool_calls` (la API lo rechaza). Test en Task 6.
- Un alumno en Windows clona en `C:\` → la recarga en caliente igual funciona (`WATCHFILES_FORCE_POLLING=true` siempre en el compose). Verificado en la Task 12 a mano.
- La pregunta tiene un mail o un teléfono → no llega al modelo ni a la memoria. Test en Task 7.

---

### Task 1: Esqueleto del repo y Estación 1 · Muelle

**Files:**
- Create: `pyproject.toml`, `uv.lock`, `Dockerfile`, `.dockerignore`, `compose.yaml`, `.env.example`, `.gitignore`, `.gitattributes`, `LICENSE`, `LICENSE-textos`, `README.md`
- Create: `taller/__init__.py`, `taller/__main__.py`
- Create: `harness/__init__.py`, `harness/config.py`, `harness/modelo.py`, `harness/agente.py`, `harness/harness.py`, `harness/app.py`, `harness/agente.yaml`
- Create: `estaciones/falsos.py`, `estaciones/1-muelle/README.md`, `estaciones/1-muelle/tests/test_muelle.py`
- Solución: `AGENTS.md`, `CLAUDE.md`, `.agents/skills/nueva-tool/SKILL.md`, `.claude/skills/nueva-tool/SKILL.md`
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Produces:
  - `harness.config.Config(academia_url: str, clave: str)` con `.pasarela_url`, `.mundo_url`, `Config.desde_env()`.
  - `harness.modelo`: `class ModeloNoDisponible(Exception)`, `class SinPresupuesto(Exception)`, `@dataclass Uso(input_tokens=0, output_tokens=0, cached_tokens=0)` con `.sumar(otro) -> None` y `.como_dict() -> dict`, `@dataclass Respuesta(mensaje: dict, uso: Uso, modelo: str)`, `class Pasarela(http, url, clave)` invocable `await p(modelo, mensajes, tools=None) -> Respuesta`. Tipo `Llamar = Callable[[list[dict], list[dict] | None], Awaitable[Respuesta]]`.
  - `harness.agente.Agente` (dataclass): `sistema: str`, `modelos: list[str] = ["kimi-k2.6", "kimi-k2.7-code-highspeed"]`, `max_vueltas: int = 6`, `herramientas: list[str] = []`, `ventana: int | None = None`, `prefetch: bool = False`, `techo_usd_sesion: float | None = None`; `cargar_agente(ruta: Path) -> Agente`.
  - `harness.harness.Harness(agente, llamar, *, registro=None, mundo=None, memoria=None, indice=None)` con `async turno(query, session_id) -> dict`.
  - `harness.app.crear_app(turno) -> FastAPI` y `harness.app.app` (instancia para uvicorn).
  - `estaciones/falsos.py`: `ModeloFalso(guion)`, `llamar_con(falso, modelo="kimi-k2.6")`, `llamada(nombre, args, id="c1")`, `MundoFalso()`, `DOCUMENTOS`.

- [ ] **Step 1: Repo e infraestructura**

```bash
mkdir -p /Users/fulfaro/monaccode/astromesh-taller-fde && cd $_ && git init -b main
```

`pyproject.toml`:
```toml
[project]
name = "astromesh-taller-fde"
version = "0.1.0"
description = "Taller FDE: un harness de agentes desde cero, estación por estación"
requires-python = ">=3.12"
license = "MIT"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "httpx>=0.27",
  "pyyaml>=6",
  "pytest>=8",
  "pytest-asyncio>=0.24",
  "ruff>=0.15",
]

[project.optional-dependencies]
forja = ["pydantic-ai-slim[openai]>=1.0"]
mercado = ["litellm>=1.60"]

[tool.uv]
package = false

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["estaciones"]
pythonpath = [".", "estaciones"]
addopts = "--import-mode=importlib -q"

[tool.ruff]
line-length = 100
target-version = "py312"
```

Run: `uv lock` → crea `uv.lock`.

`Dockerfile`:
```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/venv UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --locked
COPY . .
CMD ["uv", "run", "--no-sync", "uvicorn", "harness.app:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
```
(El venv vive en `/venv`, fuera de `/app`, así el volumen del código no lo tapa.)

`.dockerignore`:
```
.git
.venv
__pycache__
.env
```

`compose.yaml` (estación 1):
```yaml
x-harness: &harness
  build: .
  env_file:
    - path: .env
      required: false
  environment:
    WATCHFILES_FORCE_POLLING: "true"  # recarga en caliente también con el repo en C:\ (Windows)
  volumes:
    - .:/app
  extra_hosts:
    - "host.docker.internal:host-gateway"

services:
  harness:
    <<: *harness
    ports:
      - "8080:8080"

  taller:
    <<: *harness
    profiles: ["taller"]
    entrypoint: ["uv", "run", "--no-sync", "python", "-m", "taller"]

  tunel:
    image: cloudflare/cloudflared:2025.9.1
    profiles: ["tunel"]
    command: tunnel --no-autoupdate --url http://harness:8080
    depends_on:
      - harness
```
Antes de commitear, fijar el tag de cloudflared a la última release estable: `docker pull cloudflare/cloudflared:<tag>` tiene que funcionar en amd64 y arm64 (`docker manifest inspect cloudflare/cloudflared:<tag> | grep architecture`).

`.env.example`:
```
# Se completa en el Muelle, con la clave que entrega la Academia.
ACADEMIA_URL=https://academia.dev.fainansu.tech
ACADEMIA_CLAVE=
```

`.gitignore`:
```
.env
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
```

`.gitattributes`:
```
* text=auto eol=lf
*.png binary
```

`LICENSE`: texto MIT estándar, `Copyright (c) 2026 Juan Carlos Romero Fulfaro`. `LICENSE-textos`: «Los textos de `estaciones/*/README.md` se publican bajo Creative Commons Attribution 4.0 International (CC BY 4.0): https://creativecommons.org/licenses/by/4.0/».

- [ ] **Step 2: Comandos del curso (`taller/`)**

`taller/__init__.py`: vacío.

`taller/__main__.py`:
```python
"""Comandos del taller. Corren dentro del contenedor: igual en Linux, Mac y Windows."""

import subprocess
import sys
from pathlib import Path

ESTACIONES = Path("estaciones")
EXTRAS = {2: "forja", 3: "mercado", 4: "archivo"}
AYUDA = """Uso: docker compose run --rm taller <comando>

  probar N        tests de la estación N
  verificar       ruff + todos los tests
  referencia N    corre el ejemplo con el paquete del mercado de la estación N
"""


def carpeta(n: int) -> Path:
    for c in sorted(ESTACIONES.iterdir()):
        if c.is_dir() and c.name.split("-", 1)[0] == str(n):
            return c
    raise SystemExit(f"No existe la estación {n}.")


def correr(*cmd: str) -> int:
    print("$", " ".join(cmd), flush=True)
    return subprocess.call(cmd)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "ayuda"):
        print(AYUDA)
        return 0
    cmd, resto = argv[0], argv[1:]
    if cmd == "probar" and len(resto) == 1:
        return correr("pytest", str(carpeta(int(resto[0])) / "tests"))
    if cmd == "verificar":
        return (
            correr("ruff", "check", ".")
            or correr("ruff", "format", "--check", ".")
            or correr("pytest")
        )
    if cmd == "referencia" and len(resto) == 1:
        n = int(resto[0])
        script = carpeta(n) / "referencia" / "main.py"
        if not script.exists():
            raise SystemExit(f"La estación {n} no tiene referencia del mercado.")
        extra = ["--extra", EXTRAS[n]] if n in EXTRAS else []
        return correr("uv", "run", *extra, "python", str(script))
    print(AYUDA)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 3: Núcleo dado (config, modelo, agente)**

`harness/__init__.py`: vacío.

`harness/config.py`:
```python
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    academia_url: str = "https://academia.dev.fainansu.tech"
    clave: str = ""

    @property
    def pasarela_url(self) -> str:
        return f"{self.academia_url}/api/pasarela/v1"

    @property
    def mundo_url(self) -> str:
        return f"{self.academia_url}/api/mundo"

    @classmethod
    def desde_env(cls) -> "Config":
        e = os.environ
        return cls(
            academia_url=e.get("ACADEMIA_URL", cls.academia_url).rstrip("/"),
            clave=e.get("ACADEMIA_CLAVE", ""),
        )
```

`harness/modelo.py`:
```python
"""Cliente de la pasarela de la Academia (OpenAI-compatible)."""

from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass

import httpx


class ModeloNoDisponible(Exception):
    """El modelo no existe, fue retirado o el proveedor falló: conviene probar otro."""


class SinPresupuesto(Exception):
    """La pasarela cortó por techo de gasto: otro modelo no lo arregla."""


@dataclass
class Uso:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0

    def sumar(self, otro: "Uso") -> None:
        self.input_tokens += otro.input_tokens
        self.output_tokens += otro.output_tokens
        self.cached_tokens += otro.cached_tokens

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass
class Respuesta:
    mensaje: dict
    uso: Uso
    modelo: str


Llamar = Callable[[list[dict], list[dict] | None], Awaitable[Respuesta]]


def _entero(v) -> int:
    try:
        return max(int(v or 0), 0)
    except (TypeError, ValueError):
        return 0


class Pasarela:
    def __init__(self, http: httpx.AsyncClient, url: str, clave: str):
        self.http, self.url, self.clave = http, url, clave

    async def __call__(
        self, modelo: str, mensajes: list[dict], tools: list[dict] | None = None
    ) -> Respuesta:
        cuerpo: dict = {"model": modelo, "messages": mensajes}
        if tools:
            cuerpo["tools"] = tools
        try:
            r = await self.http.post(
                f"{self.url}/chat/completions",
                json=cuerpo,
                headers={"Authorization": f"Bearer {self.clave}"},
                timeout=120,
            )
        except httpx.HTTPError as e:
            raise ModeloNoDisponible(f"{modelo}: {e}") from e
        if r.status_code == 429:
            raise SinPresupuesto(r.text[:300])
        if r.status_code == 404 or r.status_code >= 500:
            raise ModeloNoDisponible(f"{modelo}: {r.status_code} {r.text[:200]}")
        r.raise_for_status()
        datos = r.json()
        u = datos.get("usage") or {}
        detalle = u.get("prompt_tokens_details") or {}
        uso = Uso(
            _entero(u.get("prompt_tokens")),
            _entero(u.get("completion_tokens")),
            _entero(u.get("cached_tokens") or detalle.get("cached_tokens")),
        )
        return Respuesta(datos["choices"][0]["message"], uso, modelo)
```

`harness/agente.py`:
```python
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Agente:
    sistema: str
    modelos: list[str] = field(default_factory=lambda: ["kimi-k2.6", "kimi-k2.7-code-highspeed"])
    max_vueltas: int = 6
    herramientas: list[str] = field(default_factory=list)
    ventana: int | None = None  # sin ventana conocida no se recorta el historial
    prefetch: bool = False
    techo_usd_sesion: float | None = None


def cargar_agente(ruta: Path) -> Agente:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    return Agente(**datos)
```

`harness/agente.yaml` (estación 1):
```yaml
sistema: |
  Sos el vendedor de la Ferretería Orbital. Respondé corto, en español rioplatense.
modelos: [kimi-k2.6]
```

- [ ] **Step 4: Falsos compartidos**

`estaciones/falsos.py`:
```python
"""Modelo, mundo y embedder falsos: los tests no usan red ni gastan plata."""

import functools
import json

from harness.modelo import Respuesta, Uso

PRODUCTOS = [
    {"id": "tornillo-8mm", "nombre": "Tornillo de 8 mm", "precio": 350, "stock": 5000},
    {"id": "martillo-impacto", "nombre": "Martillo de impacto", "precio": 12500, "stock": 40},
    {"id": "martillo-goma", "nombre": "Martillo de goma", "precio": 6800, "stock": 60},
]
DOCUMENTOS = [
    {
        "id": "pintura-epoxi-pisos",
        "titulo": "Pintura epoxi para pisos (4 l)",
        "contenido": "Curado: tránsito peatonal a las 24 horas; tránsito de vehículos a los 7 días.",
    },
    {
        "id": "garantia",
        "titulo": "Política de garantía",
        "contenido": "Las herramientas eléctricas tienen 6 meses de garantía con la factura.",
    },
]


class ModeloFalso:
    """Responde con un guion. Un paso puede ser texto, un mensaje dict o una excepción."""

    def __init__(self, guion: list):
        self.guion = list(guion)
        self.llamadas: list[dict] = []

    async def __call__(self, modelo, mensajes, tools=None) -> Respuesta:
        self.llamadas.append(
            {"modelo": modelo, "mensajes": json.loads(json.dumps(mensajes)), "tools": tools}
        )
        paso = self.guion.pop(0)
        if isinstance(paso, Exception):
            raise paso
        if isinstance(paso, str):
            paso = {"role": "assistant", "content": paso}
        return Respuesta(paso, Uso(100, 10, 0), modelo)


def llamar_con(falso: ModeloFalso, modelo: str = "kimi-k2.6"):
    return functools.partial(falso, modelo)


def llamada(nombre: str, args: dict, id: str = "c1") -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": id,
                "type": "function",
                "function": {"name": nombre, "arguments": json.dumps(args)},
            }
        ],
    }


class MundoFalso:
    def __init__(self):
        self.acciones: list[tuple[str, object]] = []
        self.presupuestos: list[list] = []

    async def productos(self, q: str, session_id: str) -> dict:
        self.acciones.append(("consultar_producto", q))
        palabras = q.lower().split()
        return {"productos": [p for p in PRODUCTOS if all(w in p["nombre"].lower() for w in palabras)]}

    async def crear_presupuesto(self, items: list, session_id: str) -> dict:
        self.acciones.append(("crear_presupuesto", items))
        self.presupuestos.append(items)
        return {"id": len(self.presupuestos), "items": items}

    async def documentos(self) -> list[dict]:
        return DOCUMENTOS
```

- [ ] **Step 5: README de la estación y tests en rojo**

`estaciones/1-muelle/README.md`:
```markdown
# Estación 1 · Muelle — Llegar y preparar el proyecto

**Construís**
- `AGENTS.md`: las reglas del proyecto para cualquier agente de código (cómo correr, qué no tocar, lint).
- `CLAUDE.md`: importa `AGENTS.md` con `@AGENTS.md` (Claude Code lee CLAUDE.md; si existe, ignora AGENTS.md).
- La skill `nueva-tool` en `.agents/skills/` (Codex, Kimi Code) y una copia idéntica en `.claude/skills/` (Claude Code). Copia, no symlink: en Windows git no crea symlinks.
- `harness/harness.py` y `harness/app.py`: `POST /run` llama al modelo y responde con el contrato.

**Astromesh lo resolvió así:** el repo del core tiene un CLAUDE.md con lo que un agente necesita para no romper nada (por ejemplo, que `ruff check` no alcanza: el CI corre `ruff format --check`).

**Probar:** `docker compose run --rm taller probar 1`
**Verificar en la Academia:** `docker compose --profile tunel up tunel`, registrar la URL en tu perfil y correr la misión `harness_responde`.
```

`estaciones/1-muelle/tests/test_muelle.py`:
```python
import re
from pathlib import Path

import pytest
import yaml
from falsos import ModeloFalso, llamar_con
from httpx import ASGITransport, AsyncClient

from harness.agente import Agente
from harness.app import crear_app
from harness.harness import Harness
from harness.modelo import ModeloNoDisponible

RAIZ = Path(__file__).resolve().parents[3]


def test_agents_md_dice_como_correr_y_que_no_tocar():
    texto = (RAIZ / "AGENTS.md").read_text(encoding="utf-8")
    assert "docker compose run --rm taller probar" in texto
    assert "estaciones/" in texto and "ruff format --check" in texto


def test_claude_md_importa_agents_md():
    assert "@AGENTS.md" in (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")


def test_la_skill_esta_en_los_dos_lugares_y_es_valida():
    a = (RAIZ / ".agents/skills/nueva-tool/SKILL.md").read_text(encoding="utf-8")
    c = (RAIZ / ".claude/skills/nueva-tool/SKILL.md").read_text(encoding="utf-8")
    assert a == c
    frente = yaml.safe_load(re.match(r"^---\n(.*?)\n---\n", a, re.S).group(1))
    assert frente["name"] == "nueva-tool"
    assert 0 < len(frente["description"]) <= 1024


async def test_turno_llama_al_modelo_con_system_y_query():
    falso = ModeloFalso(["¡Hola! Acá estoy."])
    h = Harness(Agente(sistema="Sos el vendedor."), llamar_con(falso))
    r = await h.turno("Hola", "s1")
    assert r["response"] == "¡Hola! Acá estoy."
    assert r["usage"]["input_tokens"] == 100 and r["usage"]["output_tokens"] == 10
    assert r["trace"] == []
    assert falso.llamadas[0]["mensajes"] == [
        {"role": "system", "content": "Sos el vendedor."},
        {"role": "user", "content": "Hola"},
    ]


async def _post(turno, query="Hola"):
    app = crear_app(turno)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://h") as c:
        return await c.post("/run", json={"query": query, "session_id": "s1"})


async def test_run_cumple_el_contrato():
    async def turno(q, s):
        return {"response": "ok", "usage": {"input_tokens": 1, "output_tokens": 2}, "trace": []}

    r = await _post(turno)
    assert r.status_code == 200 and r.json()["response"] == "ok"


@pytest.mark.parametrize("error", [ModeloNoDisponible("ninguno")])
async def test_run_sin_modelo_devuelve_502(error):
    async def turno(q, s):
        raise error

    r = await _post(turno)
    assert r.status_code == 502 and "ninguno" in r.json()["error"]


async def test_run_valida_la_entrada():
    async def turno(q, s):
        return {}

    app = crear_app(turno)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://h") as c:
        assert (await c.post("/run", json={"query": "x"})).status_code == 422
```

Stubs del esqueleto — `harness/harness.py`:
```python
from harness.agente import Agente
from harness.modelo import Llamar


class Harness:
    def __init__(self, agente: Agente, llamar: Llamar, *, registro=None, mundo=None,
                 memoria=None, indice=None):
        self.agente, self.llamar = agente, llamar
        self.registro, self.mundo, self.memoria, self.indice = registro, mundo, memoria, indice

    async def turno(self, query: str, session_id: str) -> dict:
        raise NotImplementedError("Estación 1: llamá al modelo con el system y la query")
```

`harness/app.py` (esqueleto):
```python
from fastapi import FastAPI

app = FastAPI(title="Harness del taller")  # Estación 1: crear_app(turno) con POST /run
```

Run: `uv run pytest estaciones/1-muelle` → Expected: FAIL (`AGENTS.md` no existe, `crear_app` no existe).

- [ ] **Step 6: CI**

`.github/workflows/ci.yml`:
```yaml
name: ci
on:
  push:
    branches: [main]
    tags: ["estacion-*"]
  pull_request:

jobs:
  main:
    if: github.ref_type != 'tag'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker compose build taller
      - run: docker compose run --rm taller verificar

  punto-de-rescate:
    if: github.ref_type == 'tag'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker compose build taller
      - name: las anteriores pasan y la estación del tag falla
        run: |
          n="${GITHUB_REF_NAME#estacion-}"
          for i in $(seq 1 $((n - 1))); do docker compose run --rm taller probar "$i"; done
          if docker compose run --rm taller probar "$n"; then
            echo "Los tests de la estación $n pasan en su punto de partida"; exit 1
          fi
```

- [ ] **Step 7: Commit del esqueleto y tag**

```bash
git add -A && git commit -m "chore(estacion-1): esqueleto del repo y consigna del Muelle"
git tag -a estacion-1 -m "Punto de partida: Estación 1 · Muelle"
```

- [ ] **Step 8: Solución — AGENTS.md, CLAUDE.md, skill**

`AGENTS.md`:
```markdown
# Taller FDE — reglas del proyecto

Un harness de agentes en Python que se construye estación por estación (`estaciones/`).

## Cómo correr
- Levantar: `docker compose up -d` (harness en http://localhost:8080).
- Tests de una estación: `docker compose run --rm taller probar N`.
- Todo junto: `docker compose run --rm taller verificar` (ruff check + ruff format --check + pytest).
- No hay Python ni uv en la máquina: todo corre en contenedores.

## Reglas
- Python 3.12, async en todo lo que hace I/O, línea de 100.
- Sin dependencias nuevas sin preguntar.
- `ruff check` no alcanza: también `ruff format --check`.
- Cada cambio en `harness/` sale con su test.

## Qué no tocar
- `estaciones/*/tests/` y `estaciones/falsos.py`: son la consigna.
- El contrato de `POST /run` (`{query, session_id}` → `{response, usage, trace}`).
- `.env`: tiene tu clave de la Academia; nunca se commitea.
```

`CLAUDE.md`:
```markdown
@AGENTS.md

## Claude Code
- Skills del proyecto en `.claude/skills/` (copia de `.agents/skills/`; mantenelas iguales).
```

`.agents/skills/nueva-tool/SKILL.md` (y copia idéntica en `.claude/skills/nueva-tool/SKILL.md`):
```markdown
---
name: nueva-tool
description: Suma una herramienta al harness del taller (schema para el modelo, función, registro y test). Usala cuando pidan agregar una tool, una acción del agente o una consulta nueva al mundo de la Ferretería.
---

# Sumar una herramienta

1. En `harness/tools.py`, registrala con el decorador `@REGISTRO.herramienta(nombre, descripcion, parametros, escribe=...)`.
   - `parametros` es JSON Schema (`type: object`, `properties`, `required`).
   - `escribe=True` si cambia algo en el mundo: la compuerta de la Aduana le va a pedir confirmación.
2. La función recibe `(args: dict, cx: ContextoTool)` y devuelve un `dict` serializable.
3. Sumá el nombre a `herramientas:` en `harness/agente.yaml`.
4. Escribí un test con `ModeloFalso` y `MundoFalso` (`estaciones/falsos.py`) que haga que el modelo pida la tool y verifique el resultado y la `trace`.
5. Corré `docker compose run --rm taller verificar`.
```

- [ ] **Step 9: Solución — `Harness.turno` y `crear_app`**

`harness/harness.py`, reemplazar `turno`:
```python
    async def turno(self, query: str, session_id: str) -> dict:
        mensajes = [
            {"role": "system", "content": self.agente.sistema},
            {"role": "user", "content": query},
        ]
        r = await self.llamar(mensajes, None)
        return {
            "response": r.mensaje.get("content") or "",
            "usage": r.uso.como_dict(),
            "trace": [],
        }
```

`harness/app.py`:
```python
import functools
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from harness.agente import cargar_agente
from harness.config import Config
from harness.harness import Harness
from harness.modelo import ModeloNoDisponible, Pasarela, SinPresupuesto

Turno = Callable[[str, str], Awaitable[dict]]


class Pedido(BaseModel):
    query: str
    session_id: str


def crear_app(turno: Turno, *, lifespan=None) -> FastAPI:
    app = FastAPI(title="Harness del taller", lifespan=lifespan)

    @app.post("/run")
    async def run(p: Pedido):
        try:
            return await turno(p.query, p.session_id)
        except (ModeloNoDisponible, SinPresupuesto) as e:
            return JSONResponse({"error": str(e)[:300]}, status_code=502)

    return app


def construir(cfg: Config) -> Harness:
    agente = cargar_agente(Path(__file__).parent / "agente.yaml")
    http = httpx.AsyncClient()
    pasarela = Pasarela(http, cfg.pasarela_url, cfg.clave)
    return Harness(agente, functools.partial(pasarela, agente.modelos[0]))


app = crear_app(construir(Config.desde_env()).turno)
```

Run: `uv run pytest estaciones/1-muelle && uv run ruff check . && uv run ruff format --check .`
Expected: PASS.

Run (con Docker): `cp .env.example .env && docker compose up -d --build && curl -s localhost:8080/run -H 'content-type: application/json' -d '{"query":"hola","session_id":"x"}'`
Expected: sin clave, 502 con `{"error": ...}` (la pasarela rechaza); con una clave real, una respuesta. `docker compose run --rm taller probar 1` → PASS.

- [ ] **Step 10: Commit de la solución**

```bash
git add -A && git commit -m "feat(estacion-1): AGENTS.md, CLAUDE.md, skill nueva-tool y POST /run"
```

### Task 2: Estación 2 · Forja — loop, tools, agente como YAML

**Files:**
- Create: `harness/mundo.py`, `harness/tools.py`, `harness/loop.py`, `harness/memoria.py`
- Modify: `harness/harness.py` (turno con loop y memoria), `harness/app.py` (`construir`), `harness/agente.yaml`
- Create: `estaciones/2-forja/README.md`, `estaciones/2-forja/tests/test_forja.py`, `estaciones/2-forja/referencia/main.py`

**Interfaces:**
- Consumes: `Respuesta`, `Uso`, `Llamar`, `Agente`, `Harness` (Task 1).
- Produces:
  - `harness.mundo.Mundo(http, url, clave)`: `async productos(q, session_id) -> dict`, `async crear_presupuesto(items, session_id) -> dict`, `async documentos() -> list[dict]`.
  - `harness.tools`: `@dataclass ContextoTool(mundo, session_id)`, `@dataclass Herramienta(nombre, descripcion, parametros, funcion, escribe=False)`, `class Registro` con `.herramienta(nombre, descripcion, parametros, escribe=False)` (decorador), `.get(nombre) -> Herramienta | None`, `.schemas(nombres) -> list[dict]`; instancia `REGISTRO` con `consultar_producto` y `crear_presupuesto` (`escribe=True`).
  - `harness.loop`: `@dataclass Turno(response: str, uso: Uso, trace: list[dict], modelo: str = "")`; `async correr(llamar, tools, registro, mensajes, cx, max_vueltas, *, compuerta=None, traza=None) -> Turno` (agrega al final de `mensajes` lo que va pasando).
  - `harness.memoria`: `@dataclass Sesion(mensajes: list[dict] = [], resumen: str = "", pendiente: dict | None = None, usd: float = 0.0)`; `class MemoriaLocal` con `async cargar(session_id) -> Sesion` (copia) y `async guardar(session_id, sesion) -> None`.

- [ ] **Step 1: README y tests en rojo**

`estaciones/2-forja/README.md`:
```markdown
# Estación 2 · Forja — El loop y las herramientas

**Construís**
- `harness/loop.py`: llama al modelo, ejecuta las tools que pide, le devuelve el resultado y repite hasta que responde; corta en `max_vueltas`.
- `harness/tools.py`: el registro de herramientas con su JSON Schema.
- `harness/memoria.py`: la sesión en memoria del proceso (en el Ascensor pasa a Postgres).
- `harness/agente.yaml`: el agente como datos.

**El mercado lo resuelve con:** Pydantic AI y OpenAI Agents SDK. `docker compose run --rm taller referencia 2` corre el mismo vendedor con Pydantic AI en ~30 líneas.

**Astromesh lo resolvió así:** 7 patrones de orquestación sobre la misma base (`astromesh/orchestration/patterns.py`) y un `ToolRegistry` con tools internas, MCP, webhook, RAG y agentes como herramienta (`astromesh/core/tools.py`).

**Probar:** `docker compose run --rm taller probar 2` · **Academia:** `consulta_producto`.
```

`estaciones/2-forja/tests/test_forja.py`:
```python
import json

from falsos import ModeloFalso, MundoFalso, llamada, llamar_con

from harness.agente import Agente
from harness.harness import Harness
from harness.memoria import MemoriaLocal
from harness.modelo import ModeloNoDisponible
from harness.tools import REGISTRO

VENDEDOR = Agente(sistema="Sos el vendedor.", herramientas=["consultar_producto"], max_vueltas=3)


def armar(guion, agente=VENDEDOR):
    falso, mundo = ModeloFalso(guion), MundoFalso()
    h = Harness(agente, llamar_con(falso), registro=REGISTRO, mundo=mundo, memoria=MemoriaLocal())
    return h, falso, mundo


def test_schemas_para_el_modelo():
    (s,) = REGISTRO.schemas(["consultar_producto"])
    assert s["type"] == "function" and s["function"]["name"] == "consultar_producto"
    assert s["function"]["parameters"]["required"] == ["q"]
    assert REGISTRO.get("crear_presupuesto").escribe is True


async def test_el_loop_ejecuta_la_tool_y_devuelve_el_resultado():
    h, falso, mundo = armar(
        [llamada("consultar_producto", {"q": "tornillo 8 mm"}), "Sale $350."]
    )
    r = await h.turno("¿Precio del tornillo de 8 mm?", "s1")
    assert r["response"] == "Sale $350."
    assert r["trace"] == [{"tool": "consultar_producto", "args": {"q": "tornillo 8 mm"}}]
    assert r["usage"]["input_tokens"] == 200
    assert mundo.acciones == [("consultar_producto", "tornillo 8 mm")]
    tool_msg = falso.llamadas[1]["mensajes"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1"
    assert json.loads(tool_msg["content"])["productos"][0]["precio"] == 350
    assert falso.llamadas[0]["tools"][0]["function"]["name"] == "consultar_producto"


async def test_tope_de_vueltas():
    pide = llamada("consultar_producto", {"q": "martillo"})
    h, _, _ = armar([pide, pide, pide])
    r = await h.turno("¿Martillos?", "s1")
    assert "vueltas" in r["response"] and len(r["trace"]) == 3


async def test_tool_desconocida_y_argumentos_rotos_no_rompen_el_turno():
    rota = llamada("consultar_producto", {})
    rota["tool_calls"][0]["function"]["arguments"] = "{no es json"
    h, falso, mundo = armar([llamada("volar", {}), rota, "Perdón."])
    r = await h.turno("Hola", "s1")
    assert r["response"] == "Perdón." and r["trace"] == [] and mundo.acciones == []
    assert "desconocida" in falso.llamadas[1]["mensajes"][-1]["content"]
    assert "inválidos" in falso.llamadas[2]["mensajes"][-1]["content"]


async def test_memoria_por_sesion():
    h, falso, _ = armar(["¡Hola Ada!", "Te llamás Ada.", "¿Quién sos?"])
    await h.turno("Me llamo Ada.", "s1")
    await h.turno("¿Cómo me llamo?", "s1")
    await h.turno("¿Cómo me llamo?", "otra")
    contenidos = [m["content"] for m in falso.llamadas[1]["mensajes"]]
    assert "Me llamo Ada." in contenidos and "¡Hola Ada!" in contenidos
    assert "Me llamo Ada." not in [m["content"] for m in falso.llamadas[2]["mensajes"]]


async def test_un_turno_que_falla_no_toca_la_sesion():
    h, falso, _ = armar(["Hola.", llamada("consultar_producto", {"q": "x"}), ModeloNoDisponible("x")])
    await h.turno("Uno", "s1")
    try:
        await h.turno("Dos", "s1")
    except ModeloNoDisponible:
        pass
    s = await h.memoria.cargar("s1")
    assert [m["content"] for m in s.mensajes] == ["Uno", "Hola."]
```

Stubs del esqueleto: `harness/loop.py`, `harness/tools.py`, `harness/memoria.py`, `harness/mundo.py` con las firmas de **Interfaces** y cuerpos `raise NotImplementedError("Estación 2: ...")`; en `tools.py` el `REGISTRO = Registro()` y las dos herramientas declaradas pero con `Registro.herramienta` sin implementar. `harness.py` no se toca todavía.

Run: `uv run pytest estaciones/2-forja` → FAIL. `uv run pytest estaciones/1-muelle` → PASS.

- [ ] **Step 2: Commit del esqueleto y tag**

```bash
git add -A && git commit -m "chore(estacion-2): esqueleto y consigna de la Forja"
git tag -a estacion-2 -m "Punto de partida: Estación 2 · Forja"
```

- [ ] **Step 3: Solución — mundo, tools, memoria**

`harness/mundo.py`:
```python
import httpx


class Mundo:
    """Cliente de la Ferretería Orbital de la Academia."""

    def __init__(self, http: httpx.AsyncClient, url: str, clave: str):
        self.http, self.url, self.clave = http, url, clave

    def _h(self, session_id: str = "") -> dict:
        return {"Authorization": f"Bearer {self.clave}", "X-Session-Id": session_id}

    @staticmethod
    def _json(r: httpx.Response) -> dict:
        try:
            datos = r.json()
        except ValueError:
            return {"error": f"HTTP {r.status_code}"}
        return {"error": f"HTTP {r.status_code}", **datos} if r.status_code >= 400 else datos

    async def productos(self, q: str, session_id: str) -> dict:
        r = await self.http.get(f"{self.url}/productos", params={"q": q}, headers=self._h(session_id))
        return self._json(r)

    async def crear_presupuesto(self, items: list, session_id: str) -> dict:
        r = await self.http.post(
            f"{self.url}/presupuestos", json={"items": items}, headers=self._h(session_id)
        )
        return self._json(r)

    async def documentos(self) -> list[dict]:
        r = await self.http.get(f"{self.url}/documentos", headers=self._h())
        return self._json(r).get("documentos", [])
```

`harness/tools.py`:
```python
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass
class ContextoTool:
    mundo: object
    session_id: str


@dataclass
class Herramienta:
    nombre: str
    descripcion: str
    parametros: dict
    funcion: Callable[[dict, ContextoTool], Awaitable[dict]]
    escribe: bool = False


class Registro:
    def __init__(self):
        self._herramientas: dict[str, Herramienta] = {}

    def herramienta(self, nombre: str, descripcion: str, parametros: dict, escribe: bool = False):
        def registrar(funcion):
            self._herramientas[nombre] = Herramienta(nombre, descripcion, parametros, funcion, escribe)
            return funcion

        return registrar

    def get(self, nombre: str) -> Herramienta | None:
        return self._herramientas.get(nombre)

    def schemas(self, nombres: list[str]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {"name": h.nombre, "description": h.descripcion, "parameters": h.parametros},
            }
            for h in (self._herramientas[n] for n in nombres)
        ]


REGISTRO = Registro()


@REGISTRO.herramienta(
    "consultar_producto",
    "Busca productos por nombre en el catálogo de la Ferretería Orbital: precio y stock.",
    {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
)
async def consultar_producto(args: dict, cx: ContextoTool) -> dict:
    return await cx.mundo.productos(str(args.get("q", "")), cx.session_id)


@REGISTRO.herramienta(
    "crear_presupuesto",
    "Crea un presupuesto con ítems del catálogo. Sólo cuando el cliente confirmó.",
    {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "producto_id": {"type": "string"},
                        "cantidad": {"type": "integer"},
                    },
                    "required": ["producto_id", "cantidad"],
                },
            }
        },
        "required": ["items"],
    },
    escribe=True,
)
async def crear_presupuesto(args: dict, cx: ContextoTool) -> dict:
    return await cx.mundo.crear_presupuesto(args.get("items", []), cx.session_id)
```

`harness/memoria.py`:
```python
import copy
from dataclasses import dataclass, field


@dataclass
class Sesion:
    mensajes: list[dict] = field(default_factory=list)  # historial, sin el system
    resumen: str = ""
    pendiente: dict | None = None
    usd: float = 0.0


class MemoriaLocal:
    """La sesión vive en el proceso: se pierde al reiniciar. En el Ascensor pasa a Postgres."""

    def __init__(self):
        self._sesiones: dict[str, Sesion] = {}

    async def cargar(self, session_id: str) -> Sesion:
        return copy.deepcopy(self._sesiones.get(session_id, Sesion()))

    async def guardar(self, session_id: str, sesion: Sesion) -> None:
        self._sesiones[session_id] = copy.deepcopy(sesion)
```

- [ ] **Step 4: Solución — el loop**

`harness/loop.py`:
```python
import json
from dataclasses import dataclass, field

from harness.modelo import Llamar, Uso
from harness.tools import ContextoTool, Registro

SIN_VUELTAS = "Me quedé sin vueltas; reformulá la pregunta."


@dataclass
class Turno:
    response: str
    uso: Uso
    trace: list[dict] = field(default_factory=list)
    modelo: str = ""


async def _ejecutar(llamada: dict, registro: Registro, cx: ContextoTool, compuerta, traza) -> dict:
    nombre = llamada["function"]["name"]
    herramienta = registro.get(nombre)
    if herramienta is None:
        return {"error": f"herramienta desconocida: {nombre}"}
    try:
        args = json.loads(llamada["function"].get("arguments") or "{}")
        if not isinstance(args, dict):
            raise TypeError
    except (ValueError, TypeError):
        return {"error": "argumentos inválidos: mandá un objeto JSON"}
    if compuerta is not None and (frenado := compuerta.decidir(herramienta, args)) is not None:
        return frenado
    resultado = await herramienta.funcion(args, cx)
    traza.append({"tool": nombre, "args": args})
    if compuerta is not None:
        compuerta.ejecutado(herramienta)
    return resultado


async def correr(
    llamar: Llamar,
    tools: list[dict],
    registro: Registro,
    mensajes: list[dict],
    cx: ContextoTool,
    max_vueltas: int,
    *,
    compuerta=None,
    traza: list[dict] | None = None,
) -> Turno:
    uso, traza = Uso(), traza if traza is not None else []
    for _ in range(max_vueltas):
        r = await llamar(mensajes, tools or None)
        uso.sumar(r.uso)
        mensajes.append(r.mensaje)
        llamadas = r.mensaje.get("tool_calls") or []
        if not llamadas:
            return Turno(r.mensaje.get("content") or "", uso, traza, r.modelo)
        for ll in llamadas:
            resultado = await _ejecutar(ll, registro, cx, compuerta, traza)
            mensajes.append(
                {
                    "role": "tool",
                    "tool_call_id": ll["id"],
                    "content": json.dumps(resultado, ensure_ascii=False),
                }
            )
    return Turno(SIN_VUELTAS, uso, traza)
```

- [ ] **Step 5: Solución — cablear el turno**

`harness/harness.py`:
```python
from harness.agente import Agente
from harness.loop import correr
from harness.memoria import MemoriaLocal
from harness.modelo import Llamar
from harness.tools import ContextoTool, Registro


class Harness:
    def __init__(self, agente: Agente, llamar: Llamar, *, registro=None, mundo=None,
                 memoria=None, indice=None):
        self.agente, self.llamar = agente, llamar
        self.registro = registro or Registro()
        self.mundo, self.indice = mundo, indice
        self.memoria = memoria or MemoriaLocal()

    async def turno(self, query: str, session_id: str) -> dict:
        s = await self.memoria.cargar(session_id)
        mensajes = [
            {"role": "system", "content": self.agente.sistema},
            *s.mensajes,
            {"role": "user", "content": query},
        ]
        t = await correr(
            self.llamar,
            self.registro.schemas(self.agente.herramientas),
            self.registro,
            mensajes,
            ContextoTool(self.mundo, session_id),
            self.agente.max_vueltas,
        )
        s.mensajes = mensajes[1:]
        await self.memoria.guardar(session_id, s)
        return {"response": t.response, "usage": t.uso.como_dict(), "trace": t.trace}
```

`harness/app.py`, en `construir`, pasar los nuevos colaboradores:
```python
from harness.memoria import MemoriaLocal
from harness.mundo import Mundo
from harness.tools import REGISTRO
...
    return Harness(
        agente,
        functools.partial(pasarela, agente.modelos[0]),
        registro=REGISTRO,
        mundo=Mundo(http, cfg.mundo_url, cfg.clave),
        memoria=MemoriaLocal(),
    )
```

`harness/agente.yaml`:
```yaml
sistema: |
  Sos el vendedor de la Ferretería Orbital. Respondé corto, en español rioplatense.
  Para precios y disponibilidad usá siempre consultar_producto; nunca inventes precios.
  Para armar un presupuesto, primero mostrá los ítems con sus precios y preguntá
  «¿Te armo el presupuesto con esto?». Usá crear_presupuesto cuando el cliente confirme.
modelos: [kimi-k2.6]
max_vueltas: 6
herramientas: [consultar_producto, crear_presupuesto]
```

- [ ] **Step 6: Referencia del mercado**

`estaciones/2-forja/referencia/main.py`:
```python
"""El mismo vendedor con Pydantic AI. Correr: docker compose run --rm taller referencia 2"""

import asyncio
import os

import httpx
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

URL = os.environ.get("ACADEMIA_URL", "https://academia.dev.fainansu.tech")
CLAVE = os.environ["ACADEMIA_CLAVE"]

modelo = OpenAIChatModel(
    "kimi-k2.6", provider=OpenAIProvider(base_url=f"{URL}/api/pasarela/v1", api_key=CLAVE)
)
vendedor = Agent(modelo, system_prompt="Sos el vendedor de la Ferretería Orbital. Respondé corto.")


@vendedor.tool_plain
async def consultar_producto(q: str) -> dict:
    """Busca productos por nombre en el catálogo: precio y stock."""
    async with httpx.AsyncClient() as http:
        r = await http.get(
            f"{URL}/api/mundo/productos", params={"q": q}, headers={"Authorization": f"Bearer {CLAVE}"}
        )
        return r.json()


async def main():
    r = await vendedor.run("¿Tienen tornillos de 8 mm? ¿A qué precio?")
    print(r.output)
    print("Lo que no ves: el loop, el schema de la tool y la memoria los resolvió la librería.")


asyncio.run(main())
```

Antes de commitear, confirmar la API vigente de pydantic-ai (`OpenAIChatModel`/`OpenAIProvider`, `tool_plain`) contra su documentación, y correrlo una vez con una clave real.

- [ ] **Step 7: Verificar y commitear**

Run: `uv lock && uv run pytest && uv run ruff check . && uv run ruff format --check .`
Expected: PASS (estaciones 1 y 2).

```bash
git add -A && git commit -m "feat(estacion-2): loop con tools, registro, memoria por sesión y agente en YAML"
```

### Task 3: Estación 3 · Mercado — router de modelos

**Files:**
- Create: `harness/router.py`, `estaciones/3-mercado/README.md`, `estaciones/3-mercado/tests/test_mercado.py`, `estaciones/3-mercado/referencia/main.py`
- Modify: `harness/app.py` (`construir` usa `Router`), `harness/agente.yaml` (`modelos` con los dos)

**Interfaces:**
- Consumes: `ModeloNoDisponible`, `SinPresupuesto`, `Respuesta` (Task 1).
- Produces: `harness.router.Router(modelo, candidatos, *, fallas_max=3, descanso_s=60.0, reloj=time.monotonic)`, invocable como `Llamar`: `await router(mensajes, tools) -> Respuesta`.

- [ ] **Step 1: README y tests en rojo**

`estaciones/3-mercado/README.md`:
```markdown
# Estación 3 · Mercado — El router de modelos

Un agente atado a un solo modelo queda mudo el día que el proveedor lo retira. Nos pasó: un
modelo retirado dejó sin respuesta a todos los agentes de desarrollo sin una alerta.

**Construís** `harness/router.py`: candidatos en orden (`kimi-k2.6` → `kimi-k2.7-code-highspeed`),
fallback cuando un modelo no existe o el proveedor falla, y un circuit breaker: 3 fallas seguidas
y el candidato descansa 60 s. Un 429 (techo de gasto) **no** es una falla del modelo: no se salta.

**El mercado lo resuelve con:** LiteLLM (`Router` con `fallbacks`) y OpenRouter como servicio.
`docker compose run --rm taller referencia 3`.

**Astromesh lo resolvió así:** `ModelRouter` con estrategias por costo, latencia o calidad,
circuit breaker de 3 fallas y 60 s, y un modelo por rol (`astromesh/core/model_router.py`).

**Probar:** `docker compose run --rm taller probar 3` · **Academia:** `fallback_modelo_retirado`.
```

`estaciones/3-mercado/tests/test_mercado.py`:
```python
import pytest
from falsos import ModeloFalso

from harness.modelo import ModeloNoDisponible, SinPresupuesto
from harness.router import Router

A, B = "kimi-k2.6", "kimi-k2.7-code-highspeed"
MSJ = [{"role": "user", "content": "hola"}]


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


async def test_usa_el_primero_si_responde():
    f = ModeloFalso(["hola"])
    r = await Router(f, [A, B])(MSJ, None)
    assert r.modelo == A and [x["modelo"] for x in f.llamadas] == [A]


async def test_fallback_si_el_primero_fue_retirado():
    f = ModeloFalso([ModeloNoDisponible("404"), "hola"])
    r = await Router(f, [A, B])(MSJ, None)
    assert r.modelo == B and [x["modelo"] for x in f.llamadas] == [A, B]


async def test_ninguno_responde():
    f = ModeloFalso([ModeloNoDisponible("a"), ModeloNoDisponible("b")])
    with pytest.raises(ModeloNoDisponible, match="a.*b"):
        await Router(f, [A, B])(MSJ, None)


async def test_el_techo_de_gasto_no_salta_al_respaldo():
    f = ModeloFalso([SinPresupuesto("techo")])
    with pytest.raises(SinPresupuesto):
        await Router(f, [A, B])(MSJ, None)
    assert len(f.llamadas) == 1


async def test_circuit_breaker_y_vuelta():
    reloj = Reloj()
    f = ModeloFalso([ModeloNoDisponible("x"), "1", ModeloNoDisponible("x"), "2",
                     ModeloNoDisponible("x"), "3", "4", "5"])
    r = Router(f, [A, B], fallas_max=3, descanso_s=60, reloj=reloj)
    for _ in range(3):
        await r(MSJ, None)
    assert (await r(MSJ, None)).modelo == B  # A descansa: ni se intenta
    assert [x["modelo"] for x in f.llamadas][-1] == B and len(f.llamadas) == 7
    reloj.t = 61
    assert (await r(MSJ, None)).modelo == A  # terminó el descanso


async def test_un_exito_resetea_las_fallas():
    # A falla, responde, falla, responde: nunca 2 fallas seguidas, así que no descansa
    f = ModeloFalso([ModeloNoDisponible("x"), "1", "2", ModeloNoDisponible("x"), "3", "4"])
    r = Router(f, [A, B], fallas_max=2)
    for _ in range(4):
        await r(MSJ, None)
    assert f.llamadas[-1]["modelo"] == A
```

Stub del esqueleto `harness/router.py`: clase `Router` con `__init__` de la interfaz y `__call__` con `raise NotImplementedError("Estación 3")`.

- [ ] **Step 2: Commit del esqueleto y tag**

```bash
git add -A && git commit -m "chore(estacion-3): esqueleto y consigna del Mercado"
git tag -a estacion-3 -m "Punto de partida: Estación 3 · Mercado"
```

- [ ] **Step 3: Solución**

`harness/router.py`:
```python
import time

from harness.modelo import ModeloNoDisponible, Respuesta


class Router:
    """Prueba los candidatos en orden. Un candidato que falla `fallas_max` veces seguidas
    descansa `descanso_s` segundos (circuit breaker)."""

    def __init__(self, modelo, candidatos: list[str], *, fallas_max: int = 3,
                 descanso_s: float = 60.0, reloj=time.monotonic):
        self.modelo, self.candidatos = modelo, list(candidatos)
        self.fallas_max, self.descanso_s, self.reloj = fallas_max, descanso_s, reloj
        self.fallas: dict[str, int] = {}
        self.hasta: dict[str, float] = {}

    def _descansa(self, c: str) -> bool:
        return self.hasta.get(c, 0.0) > self.reloj()

    def _falla(self, c: str) -> None:
        self.fallas[c] = self.fallas.get(c, 0) + 1
        if self.fallas[c] >= self.fallas_max:
            self.hasta[c] = self.reloj() + self.descanso_s
            self.fallas[c] = 0

    async def __call__(self, mensajes: list[dict], tools: list[dict] | None = None) -> Respuesta:
        errores = []
        for c in self.candidatos:
            if self._descansa(c):
                continue
            try:
                r = await self.modelo(c, mensajes, tools)
            except ModeloNoDisponible as e:
                self._falla(c)
                errores.append(f"{c}: {e}")
                continue
            self.fallas[c] = 0
            return r
        raise ModeloNoDisponible("; ".join(errores) or "todos los candidatos están descansando")
```

`harness/app.py`, en `construir`: `llamar = Router(pasarela, agente.modelos)` en lugar del `functools.partial` (borrar el import de `functools` si queda sin uso).

`harness/agente.yaml`: `modelos: [kimi-k2.6, kimi-k2.7-code-highspeed]`.

`estaciones/3-mercado/referencia/main.py`:
```python
"""Fallback con LiteLLM. Correr: docker compose run --rm taller referencia 3"""

import asyncio
import os

from litellm import Router

URL = os.environ.get("ACADEMIA_URL", "https://academia.dev.fainansu.tech") + "/api/pasarela/v1"
CLAVE = os.environ["ACADEMIA_CLAVE"]


def candidato(alias: str, modelo: str) -> dict:
    return {
        "model_name": alias,
        "litellm_params": {"model": f"openai/{modelo}", "api_base": URL, "api_key": CLAVE},
    }


router = Router(
    model_list=[candidato("principal", "no-existe"), candidato("respaldo", "kimi-k2.7-code-highspeed")],
    fallbacks=[{"principal": ["respaldo"]}],
    num_retries=0,
)


async def main():
    r = await router.acompletion("principal", [{"role": "user", "content": "Decí hola."}])
    print(r.model, "→", r.choices[0].message.content)


asyncio.run(main())
```
Confirmar la API vigente de `litellm.Router` (`model_list`, `fallbacks`, `acompletion`) y correrlo una vez.

- [ ] **Step 4: Verificar y commitear**

Run: `uv lock && uv run pytest && uv run ruff check . && uv run ruff format --check .` → PASS.

```bash
git add -A && git commit -m "feat(estacion-3): router con fallback y circuit breaker"
```

### Task 4: Estación 4 · Archivo — RAG con pgvector y embeddings de Ollama

**Files:**
- Create: `harness/rag/__init__.py`, `harness/rag/trozos.py`, `harness/rag/embeber.py`, `harness/rag/indice.py`, `harness/db.py`
- Modify: `harness/harness.py` (contexto RAG en el mensaje del usuario, sesión guarda la query original), `harness/app.py` (lifespan: pool, índice, indexación), `harness/config.py` (`database_url`, `ollama_url`, `umbral_rag`), `compose.yaml` (postgres, ollama, ollama-modelos), `pyproject.toml` (`asyncpg`; extra `archivo`)
- Create: `estaciones/4-archivo/README.md`, `estaciones/4-archivo/tests/conftest.py`, `estaciones/4-archivo/tests/test_archivo.py`, `estaciones/4-archivo/referencia/main.py`
- Modify: `estaciones/falsos.py` (sumar `EmbedderFalso`)

**Interfaces:**
- Consumes: `Mundo.documentos()` (Task 2), `Harness` (Task 2).
- Produces:
  - `harness.rag.trozos.trocear(doc: dict, max_chars: int = 400) -> list[str]`.
  - `harness.rag.embeber.Ollama(http, url, modelo="nomic-embed-text")` invocable `await e(textos: list[str], consulta: bool = False) -> list[list[float]]`. Tipo `Embeber`.
  - `harness.rag.indice.IndicePg(pool, embeber, *, umbral=0.55, k=3)`: `async preparar() -> None`, `async cargar(documentos: list[dict]) -> int` (0 si ya hay trozos), `async buscar(query: str) -> list[dict]` (`{"titulo", "texto", "similitud"}`, sólo ≥ umbral).
  - `harness.db.crear_pool(url) -> asyncpg.Pool` (con codec `jsonb` ↔ Python).
  - `harness.harness.contexto_rag(trozos: list[dict]) -> str`.
  - `falsos.EmbedderFalso` (768 dims, bolsa de palabras normalizada).

- [ ] **Step 1: Compose y dependencias**

`pyproject.toml`: sumar `"asyncpg>=0.30"` a `dependencies` y
`archivo = ["llama-index-core>=0.12", "llama-index-embeddings-ollama>=0.6"]` a los extras. `uv lock`.

`compose.yaml`: en `x-harness`, sumar

```yaml
  environment:
    WATCHFILES_FORCE_POLLING: "true"
    DATABASE_URL: postgresql://taller:taller@postgres:5432/taller
    OLLAMA_URL: http://ollama:11434
  depends_on:
    postgres:
      condition: service_healthy
    ollama-modelos:
      condition: service_completed_successfully
```

y en el servicio `taller`, que no necesita Ollama (los tests usan el embedder falso), pisar:

```yaml
    depends_on:
      postgres:
        condition: service_healthy
```

y los servicios:

```yaml
  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: taller
      POSTGRES_PASSWORD: taller
      POSTGRES_DB: taller
    volumes:
      - datos:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U taller"]
      interval: 2s
      retries: 30

  ollama:
    image: ollama/ollama:0.12.3
    volumes:
      - modelos:/root/.ollama
    healthcheck:
      test: ["CMD", "ollama", "list"]
      interval: 3s
      retries: 30

  ollama-modelos:
    image: ollama/ollama:0.12.3
    environment:
      OLLAMA_HOST: http://ollama:11434
    entrypoint: ["ollama", "pull", "nomic-embed-text"]
    depends_on:
      ollama:
        condition: service_healthy

volumes:
  datos:
  modelos:
```
Fijar el tag de `ollama/ollama` a la última release estable verificada multi-arquitectura (`docker manifest inspect`). `tunel` no cambia.

- [ ] **Step 2: README, falso y tests en rojo**

`estaciones/4-archivo/README.md`:
```markdown
# Estación 4 · Archivo — RAG: indexar y recuperar

La Ferretería tiene documentos que el modelo no conoce (`GET /api/mundo/documentos`). El RAG los
parte, los indexa y trae al prompt sólo lo que responde la pregunta. Cuando no hay nada, el agente
dice que no sabe.

**Construís** `harness/rag/`: trozos por documento, embeddings locales con Ollama
(`nomic-embed-text`, el compose lo suma en esta estación), el índice en Postgres con pgvector, la
búsqueda por similitud con un **umbral** (debajo, no hay contexto), y el contexto antepuesto al
mensaje del usuario **sólo en la llamada**: la sesión guarda la pregunta original.

**El mercado lo resuelve con:** LlamaIndex o Haystack para el pipeline; pgvector, Qdrant, Chroma o
Pinecone para el índice. `docker compose run --rm taller referencia 4`.

**Astromesh lo resolvió así:** pipeline propio con 4 chunkers, 4 vector stores y reranking
(`astromesh/rag/`). En producción el RAG nunca consulta sin filtro de cliente.

**Calibrar el umbral:** `UMBRAL_RAG` en `.env` (por defecto 0.55). Medí la similitud de una
pregunta que sí está en los documentos y de una que no, y poné el umbral en el medio.

**Probar:** `docker compose run --rm taller probar 4` · **Academia:** `consulta_documento`.
```

`estaciones/falsos.py`, sumar:
```python
import hashlib
import math
import re


class EmbedderFalso:
    """768 dimensiones, bolsa de palabras: textos que comparten palabras se parecen."""

    async def __call__(self, textos: list[str], consulta: bool = False) -> list[list[float]]:
        return [self._uno(t) for t in textos]

    @staticmethod
    def _uno(texto: str) -> list[float]:
        v = [0.0] * 768
        for p in re.findall(r"\w{4,}", texto.lower()):
            v[int(hashlib.md5(p.encode()).hexdigest(), 16) % 768] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]
```

`estaciones/4-archivo/tests/conftest.py`:
```python
import os

import pytest

from harness.db import crear_pool


@pytest.fixture
async def pool():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("Sin DATABASE_URL: corré los tests con docker compose run --rm taller")
    p = await crear_pool(url)
    await p.execute("DROP TABLE IF EXISTS trozo")
    yield p
    await p.close()
```

`estaciones/4-archivo/tests/test_archivo.py`:
```python
from falsos import DOCUMENTOS, EmbedderFalso, ModeloFalso, MundoFalso, llamar_con

from harness.agente import Agente
from harness.harness import Harness
from harness.memoria import MemoriaLocal
from harness.rag.indice import IndicePg
from harness.rag.trozos import trocear


def test_trocear_lleva_el_titulo_y_respeta_el_largo():
    doc = {"titulo": "Epoxi", "contenido": "Primera línea.\n\n" + "x " * 300}
    trozos = trocear(doc, max_chars=200)
    assert all(t.startswith("Epoxi: ") for t in trozos)
    assert all(len(t) <= 200 + len("Epoxi: ") for t in trozos)
    assert len(trozos) >= 3


async def test_indexa_una_vez_y_encuentra(pool):
    indice = IndicePg(pool, EmbedderFalso(), umbral=0.2)
    await indice.preparar()
    assert await indice.cargar(DOCUMENTOS) > 0
    assert await indice.cargar(DOCUMENTOS) == 0  # ya estaba indexado
    hallados = await indice.buscar("¿Cuántos días de curado necesita la epoxi para vehículos?")
    assert hallados and "7 días" in hallados[0]["texto"]


async def test_debajo_del_umbral_no_hay_contexto(pool):
    indice = IndicePg(pool, EmbedderFalso(), umbral=0.2)
    await indice.preparar()
    await indice.cargar(DOCUMENTOS)
    assert await indice.buscar("¿Hasta qué temperatura aguantan los guantes de nitrilo?") == []


async def test_el_contexto_va_en_la_llamada_y_no_en_la_sesion(pool):
    indice = IndicePg(pool, EmbedderFalso(), umbral=0.2)
    await indice.preparar()
    await indice.cargar(DOCUMENTOS)
    falso = ModeloFalso(["Esperá 7 días.", "De nada."])
    h = Harness(Agente(sistema="S"), llamar_con(falso), mundo=MundoFalso(),
                memoria=MemoriaLocal(), indice=indice)
    q = "¿Cuántos días de curado necesita la epoxi para vehículos?"
    await h.turno(q, "s1")
    enviado = falso.llamadas[0]["mensajes"][-1]
    assert enviado["role"] == "user" and "7 días" in enviado["content"]
    assert enviado["content"].endswith(q)
    assert falso.llamadas[0]["mensajes"][0] == {"role": "system", "content": "S"}
    await h.turno("Gracias", "s1")
    usuarios = [m["content"] for m in falso.llamadas[1]["mensajes"] if m["role"] == "user"]
    assert usuarios[0] == q
```

Stubs del esqueleto: `harness/rag/{trozos,embeber,indice}.py` y `harness/db.py` con las firmas y `NotImplementedError("Estación 4")`; `harness.py` y `app.py` sin cambios.

Run: `docker compose build taller && docker compose run --rm taller probar 4` → FAIL; `probar 1..3` → PASS.

- [ ] **Step 3: Commit del esqueleto y tag**

```bash
git add -A && git commit -m "chore(estacion-4): esqueleto y consigna del Archivo; postgres y ollama en el compose"
git tag -a estacion-4 -m "Punto de partida: Estación 4 · Archivo"
```

- [ ] **Step 4: Solución — trozos, embeddings, pool, índice**

`harness/rag/__init__.py`: vacío.

`harness/rag/trozos.py`:
```python
import re


def trocear(doc: dict, max_chars: int = 400) -> list[str]:
    """Un trozo por párrafo (o pedazo de párrafo), con el título adelante para que el trozo
    se entienda solo."""
    trozos = []
    for parrafo in re.split(r"\n\s*\n|\n", doc["contenido"]):
        parrafo = parrafo.strip()
        while parrafo:
            trozos.append(f"{doc['titulo']}: {parrafo[:max_chars]}")
            parrafo = parrafo[max_chars:].strip()
    return trozos
```

`harness/rag/embeber.py`:
```python
from collections.abc import Awaitable, Callable

import httpx

Embeber = Callable[..., Awaitable[list[list[float]]]]


class Ollama:
    def __init__(self, http: httpx.AsyncClient, url: str, modelo: str = "nomic-embed-text"):
        self.http, self.url, self.modelo = http, url.rstrip("/"), modelo

    async def __call__(self, textos: list[str], consulta: bool = False) -> list[list[float]]:
        prefijo = "search_query: " if consulta else "search_document: "  # lo pide nomic-embed-text
        r = await self.http.post(
            f"{self.url}/api/embed",
            json={"model": self.modelo, "input": [prefijo + t for t in textos]},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["embeddings"]
```

`harness/db.py`:
```python
import json

import asyncpg


async def _codecs(con: asyncpg.Connection) -> None:
    await con.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def crear_pool(url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(url, init=_codecs, min_size=1, max_size=5)
```

`harness/rag/indice.py`:
```python
from harness.rag.trozos import trocear


def _vector(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


class IndicePg:
    def __init__(self, pool, embeber, *, umbral: float = 0.55, k: int = 3):
        self.pool, self.embeber, self.umbral, self.k = pool, embeber, umbral, k

    async def preparar(self) -> None:
        await self.pool.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await self.pool.execute(
            "CREATE TABLE IF NOT EXISTS trozo ("
            " id bigserial PRIMARY KEY, doc_id text NOT NULL, titulo text NOT NULL,"
            " texto text NOT NULL, emb vector(768) NOT NULL)"
        )

    async def cargar(self, documentos: list[dict]) -> int:
        if await self.pool.fetchval("SELECT count(*) FROM trozo"):
            return 0
        filas = [(d["id"], d["titulo"], t) for d in documentos for t in trocear(d)]
        if not filas:
            return 0
        embs = await self.embeber([t for _, _, t in filas])
        await self.pool.executemany(
            "INSERT INTO trozo (doc_id, titulo, texto, emb) VALUES ($1, $2, $3, $4::vector)",
            [(*f, _vector(e)) for f, e in zip(filas, embs, strict=True)],
        )
        return len(filas)

    async def buscar(self, query: str) -> list[dict]:
        (e,) = await self.embeber([query], consulta=True)
        filas = await self.pool.fetch(
            "SELECT titulo, texto, 1 - (emb <=> $1::vector) AS similitud FROM trozo"
            " ORDER BY emb <=> $1::vector LIMIT $2",
            _vector(e),
            self.k,
        )
        return [dict(f) for f in filas if f["similitud"] >= self.umbral]
```

- [ ] **Step 5: Solución — el contexto en el turno y el arranque**

`harness/harness.py`: función de módulo y cambios en `turno`:
```python
def contexto_rag(trozos: list[dict]) -> str:
    if not trozos:
        return ""
    return "DOCUMENTOS (respondé con esto; si no alcanza, decí que no lo sabés):\n" + "\n".join(
        f"- {t['texto']}" for t in trozos
    )
```
En `turno`, antes de armar `mensajes`:
```python
        contexto = contexto_rag(await self.indice.buscar(query)) if self.indice else ""
        pregunta = f"{contexto}\n\n{query}" if contexto else query
```
usar `{"role": "user", "content": pregunta}` como último mensaje, y antes de guardar:
```python
        i = len(s.mensajes) + 1  # posición del mensaje del usuario en `mensajes`
        mensajes[i] = {"role": "user", "content": query}  # la sesión guarda la pregunta original
        s.mensajes = mensajes[1:]
```

`harness/agente.yaml`, sumar al `sistema`: «Si te paso DOCUMENTOS, respondé con ellos. Si te preguntan un dato técnico que no está en los DOCUMENTOS, decí que no lo tenés: nunca inventes datos técnicos.»

`harness/config.py`: campos `database_url: str = ""`, `ollama_url: str = "http://ollama:11434"`, `umbral_rag: float = 0.55`, leídos de `DATABASE_URL`, `OLLAMA_URL`, `UMBRAL_RAG`.

`harness/app.py`: `construir` pasa a ser asíncrono y se usa en un lifespan; el `turno` del app delega en el harness construido:
```python
import contextlib
import logging

from harness.db import crear_pool
from harness.rag.embeber import Ollama
from harness.rag.indice import IndicePg

log = logging.getLogger("harness")


async def construir(cfg: Config) -> Harness:
    agente = cargar_agente(Path(__file__).parent / "agente.yaml")
    http = httpx.AsyncClient()
    mundo = Mundo(http, cfg.mundo_url, cfg.clave)
    indice = None
    if cfg.database_url:
        pool = await crear_pool(cfg.database_url)
        indice = IndicePg(pool, Ollama(http, cfg.ollama_url), umbral=cfg.umbral_rag)
        await indice.preparar()
        try:
            log.info("trozos indexados: %s", await indice.cargar(await mundo.documentos()))
        except Exception:  # noqa: BLE001 - sin documentos el harness igual responde
            log.warning("no pude indexar los documentos; sigo sin RAG", exc_info=True)
    return Harness(
        agente,
        Router(Pasarela(http, cfg.pasarela_url, cfg.clave), agente.modelos),
        registro=REGISTRO,
        mundo=mundo,
        memoria=MemoriaLocal(),
        indice=indice,
    )


def crear_app_real(cfg: Config) -> FastAPI:
    estado: dict = {}

    @contextlib.asynccontextmanager
    async def vida(app: FastAPI):
        estado["harness"] = await construir(cfg)
        yield

    async def turno(query: str, session_id: str) -> dict:
        return await estado["harness"].turno(query, session_id)

    return crear_app(turno, lifespan=vida)


app = crear_app_real(Config.desde_env())
```
(Si el índice está vacío porque falló la indexación, `cargar` reintenta en el próximo arranque. `docker compose restart harness` alcanza.)

`estaciones/4-archivo/referencia/main.py`:
```python
"""El mismo RAG con LlamaIndex. Correr: docker compose run --rm taller referencia 4"""

import os

import httpx
from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.embeddings.ollama import OllamaEmbedding

URL = os.environ.get("ACADEMIA_URL", "https://academia.dev.fainansu.tech")
docs = httpx.get(
    f"{URL}/api/mundo/documentos", headers={"Authorization": f"Bearer {os.environ['ACADEMIA_CLAVE']}"}
).json()["documentos"]

Settings.embed_model = OllamaEmbedding("nomic-embed-text", base_url=os.environ["OLLAMA_URL"])
indice = VectorStoreIndex.from_documents([Document(text=d["contenido"], metadata={"titulo": d["titulo"]}) for d in docs])
for n in indice.as_retriever(similarity_top_k=2).retrieve("¿Cuánto curado necesita la epoxi?"):
    print(round(n.score, 3), n.node.metadata["titulo"], "→", n.node.text[:80])
print("Lo que no ves: trocear, embeber, guardar y comparar lo hizo la librería, en memoria.")
```
Confirmar la API vigente de llama-index y correrlo una vez.

- [ ] **Step 6: Calibrar el umbral con el modelo real (anotar el resultado)**

Con `docker compose up -d` y una clave real:
```bash
docker compose run --rm taller python -c "
import asyncio, httpx, os
from harness.db import crear_pool
from harness.rag.embeber import Ollama
from harness.rag.indice import IndicePg
async def m():
    i = IndicePg(await crear_pool(os.environ['DATABASE_URL']), Ollama(httpx.AsyncClient(), os.environ['OLLAMA_URL']), umbral=0)
    for q in ['¿Cuánto tengo que esperar para meter el auto sobre la epoxi?', '¿Hasta qué temperatura aguantan los guantes de nitrilo?']:
        print(q, [round(t['similitud'], 3) for t in await i.buscar(q)])
asyncio.run(m())"
```
Poner `umbral_rag` (default de `Config`) en el punto medio entre la mejor similitud de la primera y la de la segunda; anotar ambos números en el README de la estación.

- [ ] **Step 7: Verificar y commitear**

Run: `docker compose build taller && docker compose run --rm taller verificar` → PASS.

```bash
git add -A && git commit -m "feat(estacion-4): RAG con pgvector, embeddings de Ollama y umbral de «no sé»"
```

### Task 5: Estación 5 · Ascensor — contexto por niveles, presupuesto, resumen y memoria en Postgres

**Files:**
- Create: `harness/contexto.py`, `estaciones/5-ascensor/README.md`, `estaciones/5-ascensor/tests/test_ascensor.py`, `estaciones/5-ascensor/referencia/main.py`
- Modify: `harness/memoria.py` (`MemoriaPg`), `harness/harness.py` (turno arma por niveles), `harness/app.py` (`MemoriaPg` cuando hay base), `harness/agente.yaml` (`ventana`)
- Create: `estaciones/5-ascensor/tests/conftest.py` (fixture `pool` que borra `sesion`)

**Interfaces:**
- Consumes: `Sesion`, `MemoriaLocal`, `crear_pool`, `contexto_rag`.
- Produces:
  - `harness.contexto`: `estimar_tokens(texto: str) -> int`, `tokens(mensajes: list[dict]) -> int`, `presupuesto(ventana, sistema, tools, reserva=4096) -> int`, `grupos(historial) -> list[list[dict]]` (un grupo por mensaje `user` con todo lo que sigue), `recortar(historial, presupuesto) -> tuple[list[dict], list[dict]]` (entra, sale), `armar(sistema, resumen, historial, contexto, query) -> list[dict]`, `async resumir(llamar, previo, salientes) -> str`.
  - `harness.memoria.MemoriaPg(pool)` con la misma interfaz que `MemoriaLocal` y `async preparar()`.

- [ ] **Step 1: README y tests en rojo**

`estaciones/5-ascensor/README.md`:
```markdown
# Estación 5 · Ascensor — Contexto por niveles y caché  (Nuevo en Astromesh 0.64)

El modelo no recuerda nada: en cada llamada hay que volver a mandarle todo. Qué entra, en qué
orden y cuánto ocupa decide si el agente recuerda, cuánto cuesta y si el proveedor puede servir
el prompt desde caché.

    5  contexto del turno + consulta      ← cambia siempre (RAG, prefetch)
    4  historial (recortado o resumido)   ← crece al final
    3  resumen de lo que salió de la ventana
    2  esquemas de las tools              ← estable
    1  system prompt                      ← estable

Todo lo anterior al último mensaje es **prefijo**: si no cambia, Kimi lo sirve desde caché
(medimos hasta 86–88%). Un dato del RAG en el system rompe el prefijo en cada consulta.

**Construís** `harness/contexto.py`: un estimador de tokens, el presupuesto (ventana − system −
tools − reserva de respuesta), el recorte por grupos completos (nunca un `tool` sin su
`assistant`), el resumen incremental de lo que sale, y el armado en ese orden. La sesión pasa a
Postgres (`MemoriaPg`): sobrevive a un reinicio.

**El mercado lo resuelve con:** Mem0 y Letta para la memoria; el prompt caching de Anthropic y
OpenAI; LLMLingua (compresión) y DSPy (optimización offline) como noción.
`docker compose run --rm taller referencia 5` muestra `cached_tokens` creciendo con un prefijo fijo.

**Astromesh lo resolvió así (0.64.0):** `context_window` por candidato, `astromesh/core/tokens.py`,
`strategy: summary` con el rol `summarizer`, `prompts.context` al final y un aviso al cargar si el
system prompt rompe el caché. Sin ventana conocida, Astromesh no recorta: igual que acá.

**Probar:** `docker compose run --rm taller probar 5` · **Academia:** `memoria`.
```

`estaciones/5-ascensor/tests/conftest.py`:
```python
import os

import pytest

from harness.db import crear_pool


@pytest.fixture
async def pool():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("Sin DATABASE_URL: corré los tests con docker compose run --rm taller")
    p = await crear_pool(url)
    await p.execute("DROP TABLE IF EXISTS sesion")
    yield p
    await p.close()
```

`estaciones/5-ascensor/tests/test_ascensor.py`:
```python
from falsos import ModeloFalso, llamada, llamar_con

from harness.agente import Agente
from harness.contexto import armar, estimar_tokens, grupos, presupuesto, recortar
from harness.harness import Harness
from harness.memoria import MemoriaLocal, MemoriaPg, Sesion


def u(t):
    return {"role": "user", "content": t}


def a(t):
    return {"role": "assistant", "content": t}


def test_estimar_tokens():
    assert estimar_tokens("") == 0 and estimar_tokens("abcd" * 10) == 10


def test_presupuesto_descuenta_system_tools_y_reserva():
    assert presupuesto(10_000, "x" * 400, [], reserva=1000) == 10_000 - 100 - 0 - 1000  # "[]" son 0 tokens
    assert presupuesto(None, "x", [], reserva=1) is None


def test_grupos_no_separan_tool_de_su_assistant():
    h = [u("1"), llamada("consultar_producto", {}), {"role": "tool", "tool_call_id": "c1",
         "content": "{}"}, a("ok"), u("2"), a("dos")]
    assert [len(g) for g in grupos(h)] == [4, 2]


def test_recortar_deja_los_grupos_mas_nuevos():
    h = [u("a" * 400), a("b" * 400), u("c" * 40), a("d" * 40)]
    entra, sale = recortar(h, presupuesto=60)
    assert entra == h[2:] and sale == h[:2]
    assert recortar(h, presupuesto=None) == (h, [])


def test_armar_en_niveles():
    m = armar("S", "Hablaron de tornillos.", [u("hola"), a("¡hola!")], "DOCUMENTOS: x", "¿precio?")
    assert m[0] == {"role": "system", "content": "S"}
    assert m[1]["role"] == "system" and "Hablaron de tornillos." in m[1]["content"]
    assert m[2:4] == [u("hola"), a("¡hola!")]
    assert m[4] == u("DOCUMENTOS: x\n\n¿precio?")
    assert armar("S", "", [], "", "q") == [{"role": "system", "content": "S"}, u("q")]


async def test_el_prefijo_no_cambia_entre_turnos():
    falso = ModeloFalso(["uno", "dos"])
    h = Harness(Agente(sistema="S", ventana=100_000), llamar_con(falso), memoria=MemoriaLocal())
    await h.turno("primera", "s")
    await h.turno("segunda", "s")
    primera, segunda = falso.llamadas[0]["mensajes"], falso.llamadas[1]["mensajes"]
    assert segunda[: len(primera)] == primera  # lo que ya se mandó es prefijo de lo nuevo


async def test_resumen_incremental_cuando_no_entra():
    falso = ModeloFalso(["r1", "RESUMEN: se llama Ada", "r2"])
    ag = Agente(sistema="S", ventana=4096 + 1 + 40)  # entra poco historial
    h = Harness(ag, llamar_con(falso), memoria=MemoriaLocal())
    await h.turno("Me llamo Ada y " + "bla " * 40, "s")
    await h.turno("¿Cómo me llamo?", "s")
    pedido_resumen = falso.llamadas[1]["mensajes"]
    assert "Me llamo Ada" in pedido_resumen[-1]["content"]
    final = falso.llamadas[2]["mensajes"]
    assert any("RESUMEN: se llama Ada" in m["content"] for m in final if m["role"] == "system")
    s = await h.memoria.cargar("s")
    assert s.resumen == "RESUMEN: se llama Ada"
    assert all("bla bla" not in m.get("content", "") for m in s.mensajes)


async def test_memoria_pg_sobrevive(pool):
    m = MemoriaPg(pool)
    await m.preparar()
    await m.guardar("s1", Sesion(mensajes=[u("hola")], resumen="r", usd=0.5))
    s = await MemoriaPg(pool).cargar("s1")
    assert s.mensajes == [u("hola")] and s.resumen == "r" and s.usd == 0.5
    assert (await m.cargar("otra")).mensajes == []
```

Stubs: `harness/contexto.py` con las firmas y `NotImplementedError("Estación 5")`; `MemoriaPg` con los métodos y `NotImplementedError`.

- [ ] **Step 2: Commit del esqueleto y tag**

```bash
git add -A && git commit -m "chore(estacion-5): esqueleto y consigna del Ascensor"
git tag -a estacion-5 -m "Punto de partida: Estación 5 · Ascensor"
```

- [ ] **Step 3: Solución — `harness/contexto.py`**

```python
import json

from harness.modelo import Llamar


def estimar_tokens(texto: str) -> int:
    # ponytail: 4 caracteres por token; un tokenizer real si el presupuesto queda corto
    return len(texto) // 4


def tokens(mensajes: list[dict]) -> int:
    return sum(estimar_tokens(json.dumps(m, ensure_ascii=False)) for m in mensajes)


def presupuesto(ventana: int | None, sistema: str, tools: list[dict], reserva: int = 4096):
    if ventana is None:
        return None  # ventana desconocida: no se recorta (como Astromesh)
    return ventana - estimar_tokens(sistema) - estimar_tokens(json.dumps(tools)) - reserva


def grupos(historial: list[dict]) -> list[list[dict]]:
    gs: list[list[dict]] = []
    for m in historial:
        if m["role"] == "user" or not gs:
            gs.append([])
        gs[-1].append(m)
    return gs


def recortar(historial: list[dict], presupuesto: int | None) -> tuple[list[dict], list[dict]]:
    if presupuesto is None:
        return historial, []
    gs, usados, desde = grupos(historial), 0, None
    for i in range(len(gs) - 1, -1, -1):
        usados += tokens(gs[i])
        if usados > presupuesto:
            break
        desde = i
    if desde is None:
        return [], historial
    entra = [m for g in gs[desde:] for m in g]
    sale = [m for g in gs[:desde] for m in g]
    return entra, sale


def armar(sistema: str, resumen: str, historial: list[dict], contexto: str, query: str):
    mensajes = [{"role": "system", "content": sistema}]
    if resumen:
        mensajes.append({"role": "system", "content": f"Resumen de la conversación anterior:\n{resumen}"})
    pregunta = f"{contexto}\n\n{query}" if contexto else query
    return [*mensajes, *historial, {"role": "user", "content": pregunta}]


async def resumir(llamar: Llamar, previo: str, salientes: list[dict]) -> str:
    texto = "\n".join(
        f"{m['role']}: {m.get('content') or ''}" for m in salientes if m["role"] in ("user", "assistant")
    )
    pedido = (
        "Actualizá el resumen de una conversación de un vendedor de ferretería con un cliente."
        " Conservá nombres, productos, cantidades y lo que se acordó. Máximo 120 palabras.\n\n"
        f"Resumen anterior:\n{previo or '(vacío)'}\n\nMensajes nuevos:\n{texto}"
    )
    r = await llamar([{"role": "user", "content": pedido}], None)
    return (r.mensaje.get("content") or previo).strip()
```

- [ ] **Step 4: Solución — `MemoriaPg`**

En `harness/memoria.py`:
```python
from dataclasses import asdict


class MemoriaPg:
    def __init__(self, pool):
        self.pool = pool

    async def preparar(self) -> None:
        await self.pool.execute(
            "CREATE TABLE IF NOT EXISTS sesion (id text PRIMARY KEY, datos jsonb NOT NULL)"
        )

    async def cargar(self, session_id: str) -> Sesion:
        datos = await self.pool.fetchval("SELECT datos FROM sesion WHERE id = $1", session_id)
        return Sesion(**datos) if datos else Sesion()

    async def guardar(self, session_id: str, sesion: Sesion) -> None:
        await self.pool.execute(
            "INSERT INTO sesion (id, datos) VALUES ($1, $2)"
            " ON CONFLICT (id) DO UPDATE SET datos = EXCLUDED.datos",
            session_id,
            asdict(sesion),
        )
```

- [ ] **Step 5: Solución — el turno por niveles**

`harness/harness.py`, `turno` completo:
```python
    async def turno(self, query: str, session_id: str) -> dict:
        s = await self.memoria.cargar(session_id)
        tools = self.registro.schemas(self.agente.herramientas)
        contexto = contexto_rag(await self.indice.buscar(query)) if self.indice else ""
        p = presupuesto(self.agente.ventana, self.agente.sistema, tools)
        if p is not None:
            p -= estimar_tokens(contexto + query) + estimar_tokens(s.resumen)
        entra, sale = recortar(s.mensajes, p)
        if sale:
            s.resumen = await resumir(self.llamar, s.resumen, sale)
        mensajes = armar(self.agente.sistema, s.resumen, entra, contexto, query)
        base = len(mensajes)
        t = await correr(
            self.llamar, tools, self.registro, mensajes,
            ContextoTool(self.mundo, session_id), self.agente.max_vueltas,
        )
        s.mensajes = [*entra, {"role": "user", "content": query}, *mensajes[base:]]
        await self.memoria.guardar(session_id, s)
        return {"response": t.response, "usage": t.uso.como_dict(), "trace": t.trace}
```
(imports: `from harness.contexto import armar, estimar_tokens, presupuesto, recortar, resumir`). Correr `uv run pytest estaciones/2-forja estaciones/4-archivo` además de la 5: el armado nuevo tiene que mantener sus contratos.

`harness/app.py`, en `construir`: si hay `pool`, `memoria = MemoriaPg(pool); await memoria.preparar()`, si no `MemoriaLocal()`.

`harness/agente.yaml`: `ventana: 262144` (ventana de kimi-k2.6; confirmar contra la documentación de Moonshot al implementar y anotar la fuente en un comentario).

`estaciones/5-ascensor/referencia/main.py`:
```python
"""El caché del proveedor, a la vista. Correr: docker compose run --rm taller referencia 5"""

import os

import httpx

URL = os.environ.get("ACADEMIA_URL", "https://academia.dev.fainansu.tech") + "/api/pasarela/v1"
H = {"Authorization": f"Bearer {os.environ['ACADEMIA_CLAVE']}"}
PREFIJO = "Sos el vendedor de la Ferretería Orbital. " + "Regla de la casa: atendé con calma. " * 400

for i, pregunta in enumerate(["¿Abren el sábado?", "¿Hacen envíos?", "¿Tienen tarugos?"], 1):
    r = httpx.post(f"{URL}/chat/completions", headers=H, timeout=120, json={
        "model": "kimi-k2.6",
        "messages": [{"role": "system", "content": PREFIJO}, {"role": "user", "content": pregunta}],
        "max_tokens": 50,
    }).json()["usage"]
    cache = r.get("cached_tokens") or (r.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
    print(f"llamada {i}: {r['prompt_tokens']} tokens de entrada, {cache} desde caché")
print("Mismo prefijo, distinta pregunta al final: el proveedor sirve el prefijo desde caché.")
```

- [ ] **Step 6: Verificar y commitear**

Run: `docker compose run --rm taller verificar` → PASS.

```bash
git add -A && git commit -m "feat(estacion-5): contexto por niveles, presupuesto, resumen incremental y memoria en Postgres"
```

### Task 6: Estación 6 · Aduana — confirmación, PII y prefetch

**Files:**
- Create: `harness/compuertas.py`, `estaciones/6-aduana/README.md`, `estaciones/6-aduana/tests/test_aduana.py`
- Modify: `harness/harness.py` (PII, prefetch, compuerta), `harness/agente.yaml` (`prefetch: true`)

**Interfaces:**
- Consumes: `Herramienta.escribe`, `Sesion.pendiente`, `correr(..., compuerta=, traza=)`.
- Produces:
  - `harness.compuertas.tapar_pii(texto: str) -> str`.
  - `harness.compuertas.Compuerta(sesion, query)`: `.afirma: bool`, `decidir(herramienta, args) -> dict | None`, `ejecutado(herramienta) -> None`, `pendiente_confirmado() -> dict | None`.
  - `harness.compuertas.palabras_prefetch(query: str, maximo: int = 3) -> list[str]`.

- [ ] **Step 1: README y tests en rojo**

`estaciones/6-aduana/README.md`:
```markdown
# Estación 6 · Aduana — Compuertas y capas

Nada sale sin control. El modelo razona; lo que no necesita razonamiento es código determinista.

**Construís** `harness/compuertas.py`:
- **Confirmación en código:** una tool que escribe (`escribe=True`) no se ejecuta hasta que el
  cliente dice que sí, aunque el modelo la pida. La propuesta queda pendiente en la sesión y vence
  con el próximo mensaje que no sea un sí. A lo sumo una escritura por turno.
- **PII:** mails, teléfonos y DNI se tapan antes de llegar al modelo y a la memoria.
- **Prefetch:** la búsqueda que el vendedor siempre hace corre antes del modelo y entra como
  contexto del turno (nivel 5). Va a la `trace`: es una herramienta ejecutada contra el mundo.

**El mercado lo resuelve con:** Guardrails AI, NeMo Guardrails, Presidio (PII), Llama Guard.

**Astromesh lo resolvió así:** confirmación que una llamada anidada no puede darse a sí misma,
modo propose (la escritura se registra en vez de ejecutarse) y prefetch: ~55 ms de búsqueda contra
~5 s de un viaje al LLM (`astromesh/runtime/confirmacion.py`, `astromesh/runtime/prefetch.py`).

**Probar:** `docker compose run --rm taller probar 6` · **Academia:** `sin_confirmacion_no_se_escribe`.
```

`estaciones/6-aduana/tests/test_aduana.py`:
```python
from falsos import ModeloFalso, MundoFalso, llamada, llamar_con

from harness.agente import Agente
from harness.compuertas import palabras_prefetch, tapar_pii
from harness.harness import Harness
from harness.memoria import MemoriaLocal
from harness.tools import REGISTRO

ITEMS = {"items": [{"producto_id": "tornillo-8mm", "cantidad": 3}]}
AG = Agente(sistema="S", herramientas=["consultar_producto", "crear_presupuesto"])


def armar(guion, agente=AG):
    falso, mundo = ModeloFalso(guion), MundoFalso()
    h = Harness(agente, llamar_con(falso), registro=REGISTRO, mundo=mundo, memoria=MemoriaLocal())
    return h, falso, mundo


def test_tapar_pii():
    t = tapar_pii("Soy ada@orbital.com, mi cel +54 11 4567-8901 y DNI 30.123.456. Tornillo $350.")
    assert "ada@" not in t and "4567" not in t and "30.123.456" not in t
    assert "$350" in t


def test_palabras_prefetch():
    assert palabras_prefetch("¿Tienen tornillos de 8 mm? ¿A qué precio?") == ["tornillo", "precio"]
    assert palabras_prefetch("hola") == []


async def test_sin_si_no_se_escribe_y_con_si_se_escribe_una_vez():
    h, falso, mundo = armar([
        llamada("crear_presupuesto", ITEMS), "¿Te armo el presupuesto con esto?",
        "Listo, creado.",
    ])
    r1 = await h.turno("Armame un presupuesto de 3 tornillos de 8 mm.", "s")
    assert mundo.presupuestos == [] and r1["trace"] == []
    r2 = await h.turno("Sí, dale.", "s")
    assert mundo.presupuestos == [ITEMS["items"]]
    assert r2["trace"] == [{"tool": "crear_presupuesto", "args": ITEMS}]
    assert "Presupuesto creado" in falso.llamadas[2]["mensajes"][-1]["content"]


async def test_la_propuesta_vence_si_cambia_de_tema():
    h, _, mundo = armar([llamada("crear_presupuesto", ITEMS), "¿Confirmás?", "Martillos sí.", "¿Qué?"])
    await h.turno("Armame un presupuesto.", "s")
    await h.turno("¿Tienen martillos?", "s")
    await h.turno("Sí", "s")
    assert mundo.presupuestos == []


async def test_una_sola_escritura_por_turno():
    h, _, mundo = armar([
        llamada("crear_presupuesto", ITEMS), "¿Confirmás?",
        llamada("crear_presupuesto", ITEMS), "Listo.",
    ])
    await h.turno("Armame un presupuesto.", "s")
    await h.turno("Sí, dale.", "s")
    assert len(mundo.presupuestos) == 1


async def test_la_pii_no_llega_al_modelo_ni_a_la_memoria():
    h, falso, _ = armar(["Anotado."])
    await h.turno("Mi mail es ada@orbital.com", "s")
    assert "ada@orbital.com" not in str(falso.llamadas[0]["mensajes"])
    assert "ada@orbital.com" not in str((await h.memoria.cargar("s")).mensajes)


async def test_prefetch_corre_antes_y_va_a_la_traza():
    ag = Agente(sistema="S", herramientas=["consultar_producto"], prefetch=True)
    h, falso, mundo = armar(["Sale $350."], agente=ag)
    r = await h.turno("¿Tienen tornillos?", "s")
    assert mundo.acciones[0] == ("consultar_producto", "tornillo")
    assert "Tornillo de 8 mm" in falso.llamadas[0]["mensajes"][-1]["content"]
    assert r["trace"] == [{"tool": "consultar_producto", "args": {"q": "tornillo"}}]
```

Stub `harness/compuertas.py` con las firmas y `NotImplementedError("Estación 6")`.

- [ ] **Step 2: Commit del esqueleto y tag**

```bash
git add -A && git commit -m "chore(estacion-6): esqueleto y consigna de la Aduana"
git tag -a estacion-6 -m "Punto de partida: Estación 6 · Aduana"
```

- [ ] **Step 3: Solución — `harness/compuertas.py`**

```python
import re
import unicodedata

AFIRMACION = re.compile(r"^\s*(s[ií]|dale|ok|confirmo|armalo)\b", re.IGNORECASE)
PII = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    re.compile(r"\+?\d[\d\s-]{7,}\d"),
    re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}\b"),
]
VACIAS = {"tienen", "tenes", "tenés", "quiero", "cuanto", "cuánto", "sale", "cuesta",
          "armame", "presupuesto", "decime", "cuales", "cuáles", "hola", "gracias"}


def tapar_pii(texto: str) -> str:
    for patron in PII:
        texto = patron.sub("[dato oculto]", texto)
    return texto


def _plano(p: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", p) if unicodedata.category(c) != "Mn")


def palabras_prefetch(query: str, maximo: int = 3) -> list[str]:
    """Sustantivos probables: palabras de 5+ letras que no son de relleno, en singular."""
    # ponytail: heurística de palabras; un extractor con el modelo chico si no alcanza
    salida = []
    for p in re.findall(r"\w{5,}", query.lower()):
        if p in VACIAS or _plano(p) in VACIAS:
            continue
        singular = re.sub(r"(es|s)$", "", p) if p.endswith("s") else p
        if singular not in salida:
            salida.append(singular)
    return salida[:maximo]


class Compuerta:
    def __init__(self, sesion, query: str):
        self.sesion = sesion
        self.afirma = bool(AFIRMACION.match(query))
        self.escrito = False
        if not self.afirma:
            sesion.pendiente = None  # un mensaje nuevo reemplaza la propuesta vieja

    def pendiente_confirmado(self) -> dict | None:
        if self.afirma and self.sesion.pendiente is not None:
            p, self.sesion.pendiente = self.sesion.pendiente, None
            return p
        return None

    def decidir(self, herramienta, args: dict) -> dict | None:
        """None: se ejecuta. Un dict: lo que recibe el modelo en lugar de ejecutar."""
        if not herramienta.escribe:
            return None
        if self.escrito:
            return {"ya_creado": "ya se escribió en este turno; no lo repitas"}
        if not self.afirma:
            self.sesion.pendiente = {"nombre": herramienta.nombre, "args": args}
            return {"pendiente": "preguntale al cliente si confirma antes de crear el presupuesto"}
        return None

    def ejecutado(self, herramienta) -> None:
        self.escrito = self.escrito or herramienta.escribe
```

- [ ] **Step 4: Solución — el turno con compuertas**

`harness/harness.py`, `turno` completo (sustituye al de la Task 5):
```python
    async def turno(self, query: str, session_id: str) -> dict:
        query = tapar_pii(query)
        s = await self.memoria.cargar(session_id)
        cx = ContextoTool(self.mundo, session_id)
        comp, traza, partes = Compuerta(s, query), [], []
        if (p := comp.pendiente_confirmado()) is not None:
            h = self.registro.get(p["nombre"])
            res = await h.funcion(p["args"], cx)
            traza.append({"tool": p["nombre"], "args": p["args"]})
            comp.ejecutado(h)
            partes.append(f"Presupuesto creado: {json.dumps(res, ensure_ascii=False)}")
        if self.agente.prefetch and self.mundo is not None:
            for palabra in palabras_prefetch(query):
                res = await self.mundo.productos(palabra, session_id)
                traza.append({"tool": "consultar_producto", "args": {"q": palabra}})
                if res.get("productos"):
                    partes.append(f"CATÁLOGO ({palabra}): {json.dumps(res['productos'], ensure_ascii=False)}")
        if self.indice:
            partes.append(contexto_rag(await self.indice.buscar(query)))
        contexto = "\n\n".join(x for x in partes if x)
        tools = self.registro.schemas(self.agente.herramientas)
        p = presupuesto(self.agente.ventana, self.agente.sistema, tools)
        if p is not None:
            p -= estimar_tokens(contexto + query) + estimar_tokens(s.resumen)
        entra, sale = recortar(s.mensajes, p)
        if sale:
            s.resumen = await resumir(self.llamar, s.resumen, sale)
        mensajes = armar(self.agente.sistema, s.resumen, entra, contexto, query)
        base = len(mensajes)
        t = await correr(self.llamar, tools, self.registro, mensajes, cx,
                         self.agente.max_vueltas, compuerta=comp, traza=traza)
        s.mensajes = [*entra, {"role": "user", "content": query},
                      *({**m, "content": tapar_pii(m["content"])} if m.get("content") else m
                        for m in mensajes[base:])]
        await self.memoria.guardar(session_id, s)
        return {"response": tapar_pii(t.response), "usage": t.uso.como_dict(), "trace": t.trace}
```
(imports: `json`, `from harness.compuertas import Compuerta, palabras_prefetch, tapar_pii`.)

`harness/agente.yaml`: `prefetch: true`.

- [ ] **Step 5: Verificar y commitear**

Run: `docker compose run --rm taller verificar` → PASS (las 6 estaciones).

```bash
git add -A && git commit -m "feat(estacion-6): confirmación en código, PII tapada y prefetch al catálogo"
```

### Task 7: Estación 7 · Torre — trazas OpenTelemetry y `cache.hit_ratio`

**Files:**
- Create: `harness/trazas.py`, `estaciones/7-torre/README.md`, `estaciones/7-torre/tests/test_torre.py`, `estaciones/7-torre/referencia/main.py`
- Modify: `harness/loop.py` (spans), `harness/harness.py` (span del turno), `harness/app.py` (configurar exportador), `compose.yaml` (jaeger, `OTEL_EXPORTER_OTLP_ENDPOINT`), `pyproject.toml` (`opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`)

**Interfaces:**
- Consumes: `Uso`, `Respuesta.modelo`, `correr`.
- Produces: `harness.trazas.configurar(provider) -> None`, `harness.trazas.tracer()` (el tracer vigente; no-op si no se configuró), `harness.trazas.ratio_cache(uso: Uso) -> float`, `harness.trazas.configurar_otlp(endpoint: str) -> None`.

- [ ] **Step 1: Compose y dependencias**

`pyproject.toml`: `"opentelemetry-sdk>=1.27"`, `"opentelemetry-exporter-otlp-proto-http>=1.27"`. `uv lock`.

`compose.yaml`: en `x-harness.environment`, `OTEL_EXPORTER_OTLP_ENDPOINT: http://jaeger:4318`; servicio:
```yaml
  jaeger:
    image: jaegertracing/jaeger:2.10.0
    ports:
      - "16686:16686"
```
(fijar el tag a la última release estable multi-arquitectura; la imagen `jaegertracing/jaeger` v2 recibe OTLP en 4317/4318 sin configuración).

- [ ] **Step 2: README y tests en rojo**

`estaciones/7-torre/README.md`:
```markdown
# Estación 7 · Torre — Observabilidad  (Nuevo en Astromesh 0.64)

Desde la Torre se ve cada corrida: qué modelo respondió, qué tools se ejecutaron, cuántos tokens
entraron y cuántos vinieron del caché. Sin trazas, «el agente anda raro» no se puede investigar.

**Construís** `harness/trazas.py` y los spans: `harness.turno` (la corrida), `llm.complete` (cada
llamada al modelo, con `llm.model`, `llm.input_tokens`, `llm.output_tokens`, `llm.cached_tokens` y
`cache.hit_ratio`) y `tool.<nombre>`. Se exportan por OTLP a Jaeger: http://localhost:16686.

**El mercado lo resuelve con:** Langfuse, LangSmith, Arize Phoenix; todos hablan OpenTelemetry.
`docker compose run --rm taller referencia 7` imprime spans en consola con el SDK pelado.

**Astromesh lo resolvió así:** OpenTelemetry desde el día uno; `cache.hit_ratio` en el span
`llm.complete` y el span `context_fit` con lo que entró del historial (0.64.0).

**Probar:** `docker compose run --rm taller probar 7` · **Academia:** `traza_coincide`.
```

`estaciones/7-torre/tests/test_torre.py`:
```python
from falsos import ModeloFalso, MundoFalso, llamada, llamar_con
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from harness import trazas
from harness.agente import Agente
from harness.harness import Harness
from harness.memoria import MemoriaLocal
from harness.modelo import Uso
from harness.tools import REGISTRO


def test_ratio_cache():
    assert trazas.ratio_cache(Uso(1000, 10, 870)) == 0.87
    assert trazas.ratio_cache(Uso(0, 0, 0)) == 0.0


async def test_spans_de_la_corrida():
    exp = InMemorySpanExporter()
    prov = TracerProvider()
    prov.add_span_processor(SimpleSpanProcessor(exp))
    trazas.configurar(prov)
    falso = ModeloFalso([llamada("consultar_producto", {"q": "martillo"}), "Hay dos."])
    h = Harness(Agente(sistema="S", herramientas=["consultar_producto"]), llamar_con(falso),
                registro=REGISTRO, mundo=MundoFalso(), memoria=MemoriaLocal())
    r = await h.turno("¿Martillos?", "s1")
    spans = {s.name: s for s in exp.get_finished_spans()}
    assert {"harness.turno", "llm.complete", "tool.consultar_producto"} <= set(spans)
    llm = spans["llm.complete"]
    assert llm.attributes["llm.model"] == "kimi-k2.6"
    assert llm.attributes["llm.input_tokens"] == 100
    assert llm.attributes["cache.hit_ratio"] == 0.0
    turno = spans["harness.turno"]
    assert turno.attributes["session.id"] == "s1"
    assert turno.attributes["harness.tools"] == len(r["trace"]) == 1
    assert spans["tool.consultar_producto"].parent.span_id == turno.context.span_id
    trazas.configurar(None)
```

Stub `harness/trazas.py` con las firmas y `NotImplementedError("Estación 7")`.

- [ ] **Step 3: Commit del esqueleto y tag**

```bash
git add -A && git commit -m "chore(estacion-7): esqueleto y consigna de la Torre; jaeger en el compose"
git tag -a estacion-7 -m "Punto de partida: Estación 7 · Torre"
```

- [ ] **Step 4: Solución**

`harness/trazas.py`:
```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from harness.modelo import Uso

_tracer = trace.NoOpTracer()


def configurar(provider: TracerProvider | None) -> None:
    global _tracer
    _tracer = provider.get_tracer("harness") if provider else trace.NoOpTracer()


def configurar_otlp(endpoint: str) -> None:
    prov = TracerProvider(resource=Resource.create({"service.name": "harness-taller"}))
    prov.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(f"{endpoint}/v1/traces")))
    configurar(prov)


def tracer():
    return _tracer


def ratio_cache(uso: Uso) -> float:
    return round(uso.cached_tokens / uso.input_tokens, 3) if uso.input_tokens else 0.0
```

`harness/loop.py`: en `correr`, envolver la llamada al modelo:
```python
        with trazas.tracer().start_as_current_span("llm.complete") as span:
            r = await llamar(mensajes, tools or None)
            span.set_attributes({
                "llm.model": r.modelo,
                "llm.input_tokens": r.uso.input_tokens,
                "llm.output_tokens": r.uso.output_tokens,
                "llm.cached_tokens": r.uso.cached_tokens,
                "cache.hit_ratio": trazas.ratio_cache(r.uso),
            })
```
y en `_ejecutar`, la ejecución real:
```python
    with trazas.tracer().start_as_current_span(f"tool.{nombre}") as span:
        span.set_attribute("tool.args", json.dumps(args, ensure_ascii=False)[:500])
        resultado = await herramienta.funcion(args, cx)
```
(`from harness import trazas`).

`harness/harness.py`: el cuerpo de `turno` dentro de
```python
        with trazas.tracer().start_as_current_span("harness.turno") as span:
            span.set_attribute("session.id", session_id)
            ...  # cuerpo actual
            span.set_attribute("harness.tools", len(t.trace))
```
Los spans del prefetch y de la confirmación usan el mismo `tool.<nombre>` (envolver esas dos ejecuciones con `start_as_current_span`).

`harness/app.py`, al inicio de `construir`: `if ep := os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"): trazas.configurar_otlp(ep)`.

`estaciones/7-torre/referencia/main.py`:
```python
"""Spans a consola con el SDK de OpenTelemetry. Correr: docker compose run --rm taller referencia 7"""

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

prov = TracerProvider()
prov.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
tracer = prov.get_tracer("demo")
with tracer.start_as_current_span("harness.turno"):
    with tracer.start_as_current_span("llm.complete") as s:
        s.set_attributes({"llm.input_tokens": 1000, "llm.cached_tokens": 870, "cache.hit_ratio": 0.87})
print("Langfuse, LangSmith y Phoenix reciben estos mismos spans por OTLP.")
```

- [ ] **Step 5: Verificar y commitear**

Run: `docker compose run --rm taller verificar` → PASS. Con el compose arriba, una consulta por `curl` aparece en http://localhost:16686 (servicio `harness-taller`).

```bash
git add -A && git commit -m "feat(estacion-7): trazas OTLP a Jaeger con tokens y cache.hit_ratio"
```

### Task 8: Estación 8 · Bolsa — costo por corrida, por unidad y techo

**Files:**
- Create: `harness/costos.py`, `estaciones/8-bolsa/README.md`, `estaciones/8-bolsa/tests/test_bolsa.py`
- Modify: `harness/loop.py` (`Turno.usd`), `harness/harness.py` (techo, `usage.usd`, libro), `harness/app.py` (`GET /costos`), `harness/agente.yaml` (`techo_usd_sesion`)

**Interfaces:**
- Consumes: `Respuesta.modelo`, `Uso`, `Sesion.usd`.
- Produces: `harness.costos.PRECIOS_USD_POR_MILLON: dict[str, tuple[float, float, float]]`, `harness.costos.costo(modelo, uso) -> float`, `harness.costos.Libro` con `.anotar(usd)`, `.resumen() -> dict` (`corridas`, `usd_total`, `usd_por_corrida`); `Harness.libro: Libro`; `crear_app(turno, costos=None)` expone `GET /costos` si se pasa.

- [ ] **Step 1: README y tests en rojo**

`estaciones/8-bolsa/README.md`:
```markdown
# Estación 8 · Bolsa — El oficio: cotizar, operar y responder

Un agente que no se puede cobrar ni operar es un experimento.

**Construís** `harness/costos.py`: el costo de cada llamada (tokens de entrada, de caché y de
salida, con el precio del modelo que respondió), el costo de la corrida en `usage.usd`, un techo
por conversación que corta antes de llamar al modelo, y `GET /costos` con el costo por unidad.
Después ponés el precio: con un margen objetivo del 70%, ¿cuánto cobrás por consulta?

**Astromesh lo resolvió así:** Nexus mide cada corrida por cliente, aplica el techo de gasto y
factura por plan. La nube, como noción: Prisma traduce un agente de Astromesh a Vertex AI Agent
Engine; sobre 34 capacidades, 10 equivalentes, 17 parciales y 7 sin homólogo.

**Probar:** `docker compose run --rm taller probar 8` · **Academia:** `costo_por_unidad`.
```

`estaciones/8-bolsa/tests/test_bolsa.py`:
```python
import pytest
from falsos import ModeloFalso, llamar_con
from httpx import ASGITransport, AsyncClient

from harness.agente import Agente
from harness.app import crear_app
from harness.costos import Libro, costo
from harness.harness import Harness
from harness.memoria import MemoriaLocal
from harness.modelo import Uso


def test_costo_con_cache():
    # kimi-k2.6: 0.95 entrada, 0.16 caché, 4.00 salida, USD por millón
    assert costo("kimi-k2.6", Uso(1_000_000, 0, 0)) == pytest.approx(0.95)
    assert costo("kimi-k2.6", Uso(1_000_000, 1_000_000, 0)) == pytest.approx(0.16)
    assert costo("kimi-k2.6", Uso(1_000_000, 500_000, 1_000_000)) == pytest.approx(
        0.475 + 0.08 + 4.00
    )
    assert costo("modelo-desconocido", Uso(10, 0, 10)) == 0.0


def test_libro():
    lb = Libro()
    lb.anotar(0.02)
    lb.anotar(0.04)
    assert lb.resumen() == {"corridas": 2, "usd_total": 0.06, "usd_por_corrida": 0.03}
    assert Libro().resumen()["usd_por_corrida"] == 0.0


async def test_usd_en_la_respuesta_y_techo():
    falso = ModeloFalso(["uno", "dos", "tres"])
    ag = Agente(sistema="S", techo_usd_sesion=0.0002)
    h = Harness(ag, llamar_con(falso), memoria=MemoriaLocal())
    r = await h.turno("hola", "s")
    assert r["usage"]["usd"] == pytest.approx(costo("kimi-k2.6", Uso(100, 10, 0)))
    await h.turno("hola", "s")
    r3 = await h.turno("hola", "s")
    assert "techo" in r3["response"] and len(falso.llamadas) == 2
    assert h.libro.resumen()["corridas"] == 2


async def test_get_costos():
    lb = Libro()
    lb.anotar(0.01)

    async def turno(q, s):
        return {}

    app = crear_app(turno, costos=lb.resumen)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://h") as c:
        assert (await c.get("/costos")).json()["corridas"] == 1
```

Stub `harness/costos.py` con las firmas y `NotImplementedError("Estación 8")`.

- [ ] **Step 2: Commit del esqueleto y tag**

```bash
git add -A && git commit -m "chore(estacion-8): esqueleto y consigna de la Bolsa"
git tag -a estacion-8 -m "Punto de partida: Estación 8 · Bolsa"
```

- [ ] **Step 3: Solución**

`harness/costos.py`:
```python
from harness.modelo import Uso

# USD por millón de tokens: (entrada, entrada desde caché, salida). Los mismos que cobra la
# pasarela de la Academia.
PRECIOS_USD_POR_MILLON = {
    "kimi-k2.6": (0.95, 0.16, 4.00),
    "kimi-k2.7-code-highspeed": (4.00, 4.00, 4.00),
}


def costo(modelo: str, uso: Uso) -> float:
    if modelo not in PRECIOS_USD_POR_MILLON:
        return 0.0
    entrada, cache, salida = PRECIOS_USD_POR_MILLON[modelo]
    sin_cache = uso.input_tokens - uso.cached_tokens
    return (sin_cache * entrada + uso.cached_tokens * cache + uso.output_tokens * salida) / 1e6


class Libro:
    """Costo por corrida. ponytail: en memoria del proceso; Nexus lo guarda por cliente."""

    def __init__(self):
        self.usd: list[float] = []

    def anotar(self, usd: float) -> None:
        self.usd.append(usd)

    def resumen(self) -> dict:
        total = round(sum(self.usd), 6)
        n = len(self.usd)
        return {"corridas": n, "usd_total": total, "usd_por_corrida": round(total / n, 6) if n else 0.0}
```

`harness/loop.py`: `Turno` suma `usd: float = 0.0`; en `correr`, después de `uso.sumar(r.uso)`: `usd += costo(r.modelo, r.uso)` (con `usd = 0.0` al inicio) y devolver `Turno(..., usd=usd)` en los dos `return`.

`harness/harness.py`: en `__init__`, `self.libro = Libro()`. En `turno`, después de cargar la sesión:
```python
            techo = self.agente.techo_usd_sesion
            if techo is not None and s.usd >= techo:
                return {
                    "response": "Llegamos al techo de gasto de esta conversación. Te paso con una persona.",
                    "usage": {**Uso().como_dict(), "usd": 0.0},
                    "trace": [],
                }
```
y al final: `s.usd += t.usd` antes de guardar, `self.libro.anotar(t.usd)`, y `"usage": {**t.uso.como_dict(), "usd": round(t.usd, 6)}`.

`harness/app.py`: `crear_app(turno, *, lifespan=None, costos=None)`; si `costos` no es `None`:
```python
        @app.get("/costos")
        async def ver_costos():
            return costos()
```
y en `crear_app_real`, `crear_app(turno, lifespan=vida, costos=lambda: estado["harness"].libro.resumen())`.

`harness/agente.yaml`: `techo_usd_sesion: 0.25`.

- [ ] **Step 4: Verificar y commitear**

Run: `docker compose run --rm taller verificar` → PASS (las 8).

```bash
git add -A && git commit -m "feat(estacion-8): costo por corrida y por unidad, techo por conversación"
```

### Task 9: README raíz

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Escribir `README.md` con: qué es (1 párrafo), requisitos (Docker Desktop en Mac / Windows con WSL 2, Docker Engine en Linux, ~2 GB, git, clave de la Academia que se entrega en el Muelle), arranque (los comandos de la sección «Arrancar» del artefacto de diseño, en bloques separados por sistema donde difieren: `cp` vs `copy`), tabla de estaciones (estación · tag · qué construís · escenario), rescate (`git stash && git checkout estacion-N`), Windows (clonar dentro de WSL; si se clona en `C:\` funciona igual por `WATCHFILES_FORCE_POLLING`), Mac (Ollama en Docker con CPU alcanza para embeddings), túnel, licencia. Sin links a los artefactos de claude.ai: son privados.

- [ ] **Step 2: Commit**

```bash
git add README.md && git commit -m "docs: README del taller — arranque en Linux, Mac y Windows"
```

### Task 10: Ensayo de punta a punta contra la Academia (requiere clave real)

- [ ] **Step 1:** Con la clave de un participante de prueba y la Academia dev con el plan `academia-rag` desplegado: `docker compose up -d --build`, `docker compose --profile tunel up -d tunel`, registrar la URL y correr desde la Academia las 8 misiones técnicas. Expected: 8/8. Anotar el costo total del ensayo.
- [ ] **Step 2:** Por cada tag: `git checkout estacion-N && docker compose run --rm taller probar $((N-1))` pasa (N ≥ 2) y `probar N` falla. Volver a `main`.
- [ ] **Step 3:** Si algo falla, corregir en `main` y **rehacer los tags afectados** (`git tag -f`), ya que todavía no se publicaron.

### Task 11: Publicar el repo (acción externa)

- [ ] **Step 1:** Confirmar con el usuario en el chat que se crea ahora (ya aprobó nombre, visibilidad y licencia; esto es el aviso de que va a pasar).
- [ ] **Step 2:**

```bash
gh repo create monaccode/astromesh-taller-fde --public \
  --description "Taller FDE: un harness de agentes desde cero, estación por estación" \
  --source . --remote origin
git push -u origin main
for n in 1 2 3 4 5 6 7 8; do git push origin "estacion-$n"; done
```
(Los tags de a uno: más de 3 en un push no dispara workflows.)

- [ ] **Step 3:** Esperar el CI de `main` y de los 8 tags (`gh run list --limit 12`). Expected: verde; en los tags, el job `punto-de-rescate`.
- [ ] **Step 4:** Actualizar los artefactos en el repo `astromesh`: en `social/taller-fde-repo.html` cambiar el chip «Diseño aprobado · repo sin crear» por «Publicado» y el ítem «El repo no existe todavía» de «Lo que falta»; en `social/masterclass-fde.html` quitar del «Qué no vamos a decir» la línea del repo sin construir y enlazar `https://github.com/monaccode/astromesh-taller-fde`. Republicar los dos artefactos (mismo archivo → mismo URL).

### Task 12: Prueba a mano en Mac y Windows (con el usuario)

- [ ] **Step 1:** Mac (Apple silicon): clonar, `git checkout estacion-1`, `cp .env.example .env`, `docker compose up -d`, `docker compose run --rm taller verificar` en `main`. Anotar tiempo de la primera descarga.
- [ ] **Step 2:** Windows 11 con Docker Desktop + WSL 2: lo mismo, una vez clonando dentro de WSL y otra en `C:\`. En `C:\`, editar `harness/agente.yaml` y confirmar que uvicorn recarga (`docker compose logs harness`). Confirmar que `git checkout estacion-4` no deja archivos con CRLF (`git ls-files --eol | grep crlf` vacío).
- [ ] **Step 3:** Anotar los resultados en `estaciones/1-muelle/README.md` («Probado en …») y commitear.
