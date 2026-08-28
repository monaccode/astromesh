FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock* ./
COPY README.md ./

# `astromesh-glyph` es un path source del monorepo (`[tool.uv.sources]`), así que
# uv lo necesita presente para resolver. Los otros siblings (`astromesh-adk`,
# `astromesh-orbit`, `astromesh-forge`) están en `.dockerignore` a propósito: no
# van a la imagen de producción, y `--frozen` evita que uv les pida metadata.
COPY astromesh-glyph/ astromesh-glyph/

# Dos syncs, que es el patrón de capas de uv: primero sólo las dependencias
# —capa cacheable que no cambia al tocar el código— y después el proyecto, ya
# con el fuente presente. Un solo sync antes de copiar `astromesh/` no puede
# construir el proyecto y falla.
#
# `--extra redis` por la misma razón que `--extra glyph`: `config/agents/` trae
# un agente con memoria conversacional en redis, y sin el extra el runtime no
# puede construir ese backend. Desde 0.44.0 eso se NOTA —antes el backend no se
# construía nunca y la falta pasaba desapercibida—, así que la imagen instala lo
# que su propia config declara.
#
# `--extra glyph` porque `config/agents/` trae un agente con `spec.program`, y sin
# el extra ese agente queda en `draft` con error — deliberadamente, para no
# degradarse en silencio a un patrón 400x más caro.
RUN uv sync --frozen --no-dev --extra glyph --extra redis --no-install-project

COPY astromesh/ astromesh/
COPY config/ config/

RUN uv sync --frozen --no-dev --extra glyph --extra redis

EXPOSE 8000

# El venv directo, no `uv run`: uv re-resuelve en cada arranque y fallaría
# pidiendo la metadata de los siblings que la imagen no lleva. Sacarlo del
# arranque además hace que el contenedor no dependa de uv en runtime.
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "astromesh.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
