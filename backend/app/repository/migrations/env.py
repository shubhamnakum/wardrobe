from alembic import context
from sqlalchemy import Connection

from app.config import get_settings
from app.repository.db import make_engine
from app.repository.models import Base

target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    # render_as_batch: SQLite cannot ALTER most things in place; batch mode recreates the table.
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


# Programmatic use (app startup/tests) passes a connection; the CLI builds its own from settings.
connection = context.config.attributes.get("connection")
if connection is not None:
    _run(connection)
else:
    db_path = get_settings().db_path
    assert db_path is not None
    with make_engine(db_path).begin() as conn:
        _run(conn)
