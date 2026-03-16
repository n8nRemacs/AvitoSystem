import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.middleware.auth import ApiKeyAuthMiddleware
from src.middleware.error_handler import ErrorHandlerMiddleware
from src.routers import health, sessions, messenger, calls, search, farm, auth_browser, realtime
from src.workers.ws_manager import ws_manager

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("xapi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("X-API starting on %s:%s", settings.host, settings.port)
    ws_manager.init(asyncio.get_running_loop())
    yield
    await ws_manager.stop_all()
    logger.info("X-API shutting down")


app = FastAPI(
    title="Avito X-API Gateway",
    version="0.1.0",
    description="SaaS gateway to Avito mobile API",
    lifespan=lifespan,
)

# Middleware (order matters: outermost = first to run)
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(ApiKeyAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(messenger.router)
app.include_router(calls.router)
app.include_router(search.router)
app.include_router(farm.router)
app.include_router(auth_browser.router)
app.include_router(realtime.router)
