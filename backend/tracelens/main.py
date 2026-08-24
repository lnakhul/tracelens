"""FastAPI application factory and TraceLens executable entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from tracelens.api.routes import router as api_router
from tracelens.config import Settings, parse_args
from tracelens.database.session import create_engine, create_session_factory, initialize_database
from tracelens.proxy.routes import router as proxy_router
from tracelens.services.failure_analysis import FailureAnalysisService
from tracelens.services.traces import TraceService


def create_app(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    ai_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Create an application configured for one local upstream target."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database_engine = create_engine(settings.database_path)
        await initialize_database(database_engine)
        app.state.trace_service = TraceService(create_session_factory(database_engine))
        app.state.http_client = httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=False,
            transport=transport,
        )
        app.state.failure_analysis_client = httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            transport=ai_transport,
        )
        app.state.failure_analysis_service = FailureAnalysisService(
            endpoint=settings.ai_endpoint,
            api_key=settings.ai_api_key,
            model=settings.ai_model,
            http_client=app.state.failure_analysis_client,
        )
        try:
            yield
        finally:
            await app.state.http_client.aclose()
            await app.state.failure_analysis_client.aclose()
            await database_engine.dispose()

    app = FastAPI(title="TraceLens", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(api_router)
    app.include_router(proxy_router)
    return app


def main() -> None:
    """Run the local TraceLens server from the command line."""

    import uvicorn

    settings = parse_args()
    uvicorn.run(create_app(settings), host=settings.bind_host, port=settings.port)


if __name__ == "__main__":
    main()
