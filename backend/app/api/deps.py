"""FastAPI dependencies: shared objects that route functions receive as arguments."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine

from app.repository.unit_of_work import UnitOfWork
from app.storage import StorageService


def get_engine(request: Request) -> Engine:
    """Return the database engine created at application startup."""
    engine: Engine = request.app.state.engine
    return engine


def get_storage(request: Request) -> StorageService:
    """Return the file storage service created at application startup."""
    storage: StorageService = request.app.state.storage
    return storage


def get_uow(engine: Annotated[Engine, Depends(get_engine)]) -> Iterator[UnitOfWork]:
    """Open one unit of work (database transaction) for the duration of a request."""
    with UnitOfWork(engine) as uow:
        yield uow


EngineDep = Annotated[Engine, Depends(get_engine)]
StorageDep = Annotated[StorageService, Depends(get_storage)]
UowDep = Annotated[UnitOfWork, Depends(get_uow)]
