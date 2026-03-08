FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock* ./
COPY README.md ./
RUN uv sync --no-dev

COPY astromesh/ astromesh/
COPY config/ config/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "astromesh.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
