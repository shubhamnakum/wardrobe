"""Exception handlers that turn errors into short, consistent JSON responses."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.taxonomy import TaxonomyError

log = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Attach the app's exception handlers (taxonomy errors -> 422, anything else -> short 500)."""

    @app.exception_handler(TaxonomyError)
    async def invalid_value(_: Request, exc: TaxonomyError) -> JSONResponse:
        """Report values outside the taxonomy in the same shape as FastAPI's own 422 errors."""
        detail = []
        for message in exc.errors:
            field, _sep, text = message.partition(": ")
            detail.append({"loc": ["body", *field.split(".")], "msg": text or field})
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        """Log the real error locally and return a short, trace-free 500."""
        # Full trace goes to the local log; the client gets a short, trace-free message (NFR-012).
        log.error("Unhandled error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "Something went wrong. Please try again.",
            },
        )
