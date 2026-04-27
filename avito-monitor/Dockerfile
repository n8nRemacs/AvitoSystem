FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv

WORKDIR /app

# --- builder stage: install deps into /opt/venv -----------------------------
FROM base AS builder

COPY pyproject.toml ./
COPY uv.lock* ./

# Include dev group so we can run pytest/ruff inside the dev image. Strip --no-dev
# in a separate prod target later if image size becomes an issue.
RUN uv sync --no-install-project

# --- runtime stage ----------------------------------------------------------
FROM base AS runtime

COPY --from=builder /opt/venv /opt/venv

COPY app /app/app
COPY avito_mcp /app/avito_mcp
COPY shared /app/shared
COPY scripts /app/scripts
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
# tests/ is excluded from the build context (.dockerignore) and is mounted as a
# bind volume in docker-compose.yml so pytest can run inside the running container.

EXPOSE 8000 9000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
