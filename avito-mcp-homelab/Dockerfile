FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Slim dep set — only what avito-mcp actually needs at runtime.
# (No SQLAlchemy / Alembic / Redis / Aiogram — those belong to the dev
# avito-monitor stack, not this thin MCP wrapper.)
RUN pip install --no-cache-dir \
        "mcp>=1.0" \
        "starlette>=0.41" \
        "uvicorn[standard]>=0.32" \
        "httpx>=0.27" \
        "pydantic>=2.9" \
        "pydantic-settings>=2.6"

COPY avito_mcp /app/avito_mcp
COPY shared /app/shared
# Minimal shim of the dev tree's `app/` package — only the bits avito_mcp's
# url-parser tool reaches into (services/url_parser.py + data/*.json). NOT
# the full FastAPI app.
COPY app /app/app

EXPOSE 9000

# --loop asyncio matches the xapi-homelab pattern (LXC/Proxmox quirk that
# bites uvloop on this host).
CMD ["python", "-m", "avito_mcp"]
