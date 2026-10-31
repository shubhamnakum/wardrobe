"""Application entry point: builds the FastAPI app and manages start-up / shut-down."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import garments, health, taxonomy
from app.api.errors import register_error_handlers
from app.config import get_settings
from app.config.logging import setup_logging
from app.repository.db import make_engine, migrate
from app.storage import StorageService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start-up and shut-down work: migrate the database, create shared services, clean up."""
    settings = get_settings()
    assert settings.db_path is not None and settings.storage_root is not None
    engine = make_engine(settings.db_path)
    migrate(engine)
    app.state.engine = engine
    app.state.storage = StorageService(settings.storage_root)
    try:
        yield
    finally:
        engine.dispose()


def create_app() -> FastAPI:
    """Build the FastAPI application: logging, error handlers and routers."""
    setup_logging(get_settings())
    app = FastAPI(title="Wardrobe API", version="0.1.0", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(garments.router)
    app.include_router(taxonomy.router)
    return app


app = create_app()
