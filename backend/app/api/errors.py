import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Full trace goes to the local log; the client gets a short, trace-free message (NFR-012).
        log.error("Unhandled error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "Something went wrong. Please try again.",
            },
        )
