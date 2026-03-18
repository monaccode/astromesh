FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY astromesh_cloud ./astromesh_cloud

RUN python -m pip install --upgrade pip && \
    python -m pip install .

EXPOSE 8001

CMD ["uvicorn", "astromesh_cloud.main:app", "--host", "0.0.0.0", "--port", "8001"]
