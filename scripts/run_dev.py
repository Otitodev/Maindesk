"""Local dev server entrypoint — use instead of the bare `uvicorn` CLI on Windows.

`uvicorn app.main:app` hardcodes a ProactorEventLoop on Windows
(uvicorn/loops/asyncio.py picks it whenever Server.run() creates its own
loop). psycopg's async mode — used by langgraph-checkpoint-postgres's
AsyncPostgresSaver in app.agents.orchestrator — cannot run under
ProactorEventLoop and raises on startup.

Calling Server.serve() directly (instead of Server.run()) sidesteps that
loop selection entirely: serve() just runs in whatever loop is already
active, so we control the loop ourselves via asyncio.run(loop_factory=...).
No effect on Linux, where SelectorEventLoop is already uvicorn's default —
this is what the ECS deploy target runs regardless (see Dockerfile).

Usage:
    .venv\\Scripts\\python scripts\\run_dev.py [--host 0.0.0.0] [--port 8000]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Running as `python scripts/run_dev.py` puts scripts/ on sys.path[0], not the
# repo root, so `app` wouldn't be importable without this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn


async def _serve(host: str, port: int) -> None:
    config = uvicorn.Config("app.main:app", host=host, port=port)
    server = uvicorn.Server(config)
    await server.serve()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.run(_serve(args.host, args.port), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(_serve(args.host, args.port))


if __name__ == "__main__":
    main()
