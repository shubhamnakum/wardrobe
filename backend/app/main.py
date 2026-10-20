from fastapi import FastAPI

from app.api import health
from app.api.errors import register_error_handlers
from app.config import get_settings
from app.config.logging import setup_logging


def create_app() -> FastAPI:
    setup_logging(get_settings())
    app = FastAPI(title="Wardrobe API", version="0.1.0")
    register_error_handlers(app)
    app.include_router(health.router)
    return app


app = create_app()
