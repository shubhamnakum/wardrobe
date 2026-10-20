from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.main import create_app
from app.repository.db import make_engine, migrate
from app.repository.models import AttributeEvidence, Base, Garment, Outfit, Processing
from app.repository.seed import seed_wardrobe

TABLES = {
    "garment", "garment_image", "processing", "attribute_evidence",
    "outfit", "outfit_item", "preference", "feedback", "usage_event",
}  # fmt: skip


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    e = make_engine(tmp_path / "t.db")
    migrate(e)
    yield e
    e.dispose()


def test_fresh_db_gets_all_tables(engine: Engine) -> None:
    assert TABLES <= set(inspect(engine).get_table_names())


def test_migrate_is_idempotent(engine: Engine) -> None:
    migrate(engine)
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM alembic_version")).scalar() == 1


def test_models_match_migrations(engine: Engine) -> None:
    """Fails when a model changes without a new migration."""
    with engine.connect() as c:
        diff = compare_metadata(MigrationContext.configure(c), Base.metadata)
    assert diff == []


def test_pragmas_set_on_connect(engine: Engine) -> None:
    with engine.connect() as c:
        assert c.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert c.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_foreign_keys_enforced(engine: Engine) -> None:
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        s.add(AttributeEvidence(garment_id="missing", attribute_name="color", source="model"))


def test_check_constraints(engine: Engine) -> None:
    with Session(engine) as s, s.begin():
        s.add(Garment(id="g", display_name="x"))
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        s.add(Processing(id="p", garment_id="g", status="bogus"))
    with pytest.raises(IntegrityError), Session(engine) as s, s.begin():
        s.add(Outfit(id="o", score_out_of_10=11))
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text("UPDATE garment SET style_tags = 'not json' WHERE id = 'g'"))


def test_json_roundtrip_and_none_is_sql_null(engine: Engine) -> None:
    with Session(engine) as s, s.begin():
        s.add(Garment(id="g", display_name="x", style_tags=["casual"]))
    with Session(engine) as s:
        g = s.get(Garment, "g")
        assert g is not None and g.style_tags == ["casual"] and g.secondary_colors is None
    with engine.connect() as c:
        assert c.execute(text("SELECT secondary_colors FROM garment")).scalar() is None


def test_cascade_delete_garment_removes_evidence(engine: Engine) -> None:
    with Session(engine) as s, s.begin():
        s.add(Garment(id="g", display_name="x"))
        s.flush()  # no relationship() defined, so order parent-before-child explicitly
        s.add(
            AttributeEvidence(
                garment_id="g", attribute_name="color", source="user", confirmed_at="2026-01-01"
            )
        )
    with Session(engine) as s, s.begin():
        s.delete(s.get_one(Garment, "g"))
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(AttributeEvidence)) == 0


def test_seed_wardrobe(engine: Engine) -> None:
    ids = seed_wardrobe(engine)
    with Session(engine) as s:
        assert len(ids) == s.scalar(select(func.count()).select_from(Garment)) > 10


def test_app_startup_migrates_configured_db() -> None:
    with TestClient(create_app()):
        pass
    db_path = get_settings().db_path
    assert db_path is not None
    e = make_engine(db_path)
    assert TABLES <= set(inspect(e).get_table_names())
    e.dispose()
