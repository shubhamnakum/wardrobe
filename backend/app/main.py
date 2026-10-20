from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.api.errors import register_error_handlers
from app.config import get_settings
from app.config.logging import setup_logging
from app.repository.db import make_engine, migrate


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    assert settings.db_path is not None
    engine = make_engine(settings.db_path)
    try:
        migrate(engine)
    finally:
        engine.dispose()
    yield


def create_app() -> FastAPI:
    setup_logging(get_settings())
    app = FastAPI(title="Wardrobe API", version="0.1.0", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(health.router)
    return app


app = create_app()
