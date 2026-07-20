import asyncio
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

if sys.platform == "win32":
    # psycopg's async mode (used by langgraph-checkpoint-postgres's
    # AsyncPostgresSaver) requires a SelectorEventLoop; Windows has defaulted
    # to ProactorEventLoop since Python 3.8. Only affects local dev — the
    # ECS deploy target is Linux, where this distinction doesn't exist.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app import clinic_config
from app.agents.orchestrator import build_graph
from app.chat.router import router as chat_router
from app.config import get_settings
from app.dashboard.router import router as staff_router
from app.gateway.adapters.email import router as email_router
from app.onboarding.router import router as onboarding_router
from app.gateway.adapters.email_client import close_client as close_email_client
from app.gateway.adapters.evolution_client import close_client as close_evolution_client
from app.gateway.adapters.web import router as web_router
from app.gateway.adapters.whatsapp import router as whatsapp_router
from app.gateway.limiter import limiter
from app.gateway.demo_inbox import router as demo_inbox_router
from app.gateway.readiness import router as readiness_router
from app.voice.router import router as voice_router
from app.voice.webrtc_router import close as close_webrtc_handler
from app.voice.webrtc_router import router as voice_web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.exit_stack = AsyncExitStack()
    await app.state.exit_stack.__aenter__()
    app.state.graph = await build_graph(app.state)
    await clinic_config.refresh()  # load clinic persona/hours into the cache
    try:
        yield
    finally:
        await close_evolution_client()
        await close_email_client()
        await close_webrtc_handler()
        await app.state.exit_stack.aclose()


app = FastAPI(title="MainDesk", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(whatsapp_router)
app.include_router(web_router)
app.include_router(email_router)
app.include_router(staff_router)
app.include_router(onboarding_router)
app.include_router(chat_router)
app.include_router(readiness_router)
app.include_router(demo_inbox_router)
app.include_router(voice_router)
app.include_router(voice_web_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# Serve the marketing landing page at `/` and its static assets under the
# same origin as the app. Mount LAST so all API routers above take priority.
# `html=True` makes StaticFiles serve `index.html` when a directory is hit.
_landing_dir = Path(__file__).resolve().parent.parent / "landingpage"
if _landing_dir.is_dir():
    app.mount("/", StaticFiles(directory=_landing_dir, html=True), name="landing")
