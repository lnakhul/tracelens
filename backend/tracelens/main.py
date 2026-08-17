"""FastAPI application factory and TraceLens executable entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from tracelens.api.routes import router as api_router
from tracelens.config import Settings, parse_args


def create_app(settings: Settings) -> FastAPI:
    """Create an application configured for one local upstream target."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.http_client = httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=False,
        )
        try:
            yield
        finally:
            await app.state.http_client.aclose()

    app = FastAPI(title="TraceLens", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(api_router)
    return app


def main() -> None:
    """Run the local TraceLens server from the command line."""

    import uvicorn

    settings = parse_args()
    uvicorn.run(create_app(settings), host=settings.bind_host, port=settings.port)


if __name__ == "__main__":
    main()
