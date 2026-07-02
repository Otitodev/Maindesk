from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
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
        await app.state.exit_stack.aclose()


app = FastAPI(title="HealthDesk AI", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(whatsapp_router)
app.include_router(web_router)
app.include_router(email_router)
app.include_router(staff_router)
app.include_router(onboarding_router)
app.include_router(chat_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
