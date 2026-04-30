FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- builder stage: install deps into /opt/venv -----------------------------
FROM base AS builder

COPY pyproject.toml ./

# Use pip (not uv) to avoid signalfd seccomp panic on PVE kernel 6.17+.
# Install all runtime + dev deps from pyproject.toml dependency lists.
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install \
        "fastapi>=0.115" \
        "uvicorn[standard]>=0.32" \
        "pydantic>=2.9" \
        "pydantic-settings>=2.6" \
        "sqlalchemy[asyncio]>=2.0.36" \
        "asyncpg>=0.30" \
        "alembic>=1.13" \
        "argon2-cffi>=23.1" \
        "itsdangerous>=2.2" \
        "jinja2>=3.1" \
        "python-multipart>=0.0.12" \
        "structlog>=24.4" \
        "httpx>=0.27" \
        "redis>=5.2" \
        "taskiq>=0.11" \
        "taskiq-redis>=1.0" \
        "aiogram>=3.13" \
        "aiohttp-socks>=0.10" \
        "mcp>=1.0" \
        "starlette>=0.41" \
        "openai>=1.50" \
        "pytest>=8.3" \
        "pytest-asyncio>=0.24" \
        "pytest-mock>=3.14" \
        "respx>=0.21" \
        "ruff>=0.7" \
        "mypy>=1.13"

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
