from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from findash.core.database import (
    create_database_engine,
    create_session_factory,
)
from findash.core.errors import register_error_handlers
from findash.core.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API. The database is only opened when the app starts."""
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(resolved.investments_database_url)
        app.state.investments_session_factory = create_session_factory(engine)
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="Financial dashboard API", lifespan=lifespan)
    register_error_handlers(app)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
