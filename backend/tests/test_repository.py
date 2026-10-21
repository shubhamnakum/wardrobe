import re
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from app.repository.db import make_engine, migrate
from app.repository.garments import GarmentFilter
from app.repository.models import Processing
from app.repository.unit_of_work import UnitOfWork


@pytest.fixture
def engine() -> Iterator[Engine]:
    e = make_engine(":memory:")
    migrate(e)
    yield e
    e.dispose()


def _count(engine: Engine) -> int:
    with UnitOfWork(engine) as uow:
        return uow.garments.list()[1]


# --- unit of work: commit / rollback / FK (BE-E1-S3-T1, T4) ---------------------------------


def test_commit_on_clean_exit(engine: Engine) -> None:
    with UnitOfWork(engine) as uow:
        gid = uow.garments.add("White T-shirt", category="top").id
    with UnitOfWork(engine) as uow:
        g = uow.garments.get(gid)
        assert g is not None and g.display_name == "White T-shirt"


def test_rollback_on_exception(engine: Engine) -> None:
    with pytest.raises(RuntimeError), UnitOfWork(engine) as uow:
        uow.garments.add("Ghost")
        raise RuntimeError("boom")
    assert _count(engine) == 0


def test_fk_violation_raises_and_rolls_back_whole_unit(engine: Engine) -> None:
    with pytest.raises(IntegrityError), UnitOfWork(engine) as uow:
        uow.garments.add("Will not survive")
        uow.evidence.add("missing-garment", "color", "red", "model")
    assert _count(engine) == 0


def test_outfit_with_unknown_garment_leaves_no_outfit(engine: Engine) -> None:
    with pytest.raises(IntegrityError), UnitOfWork(engine) as uow:
        uow.outfits.create([("missing", "top")], style_label="x")
    with UnitOfWork(engine) as uow:
        assert uow.outfits.list() == []


def test_check_constraint_violation_rolls_back(engine: Engine) -> None:
    with pytest.raises(IntegrityError), UnitOfWork(engine) as uow:
        oid = uow.outfits.create([]).id
        uow.feedback.add(oid, "bogus-action")
    with UnitOfWork(engine) as uow:
        assert uow.outfits.list() == []


def test_unknown_field_rejected(engine: Engine) -> None:
    with pytest.raises(ValueError), UnitOfWork(engine) as uow:
        uow.garments.add("x", colour="red")


# --- garments (T2) --------------------------------------------------------------------------


def _seed(uow: UnitOfWork) -> dict[str, str]:
    g = uow.garments
    return {
        "tee": g.add(
            "White T-shirt",
            category="top",
            primary_color="white",
            pattern="solid",
            style_tags=["casual", "classic"],
            season_tags=["summer"],
        ).id,
        "shirt": g.add(
            "Striped shirt",
            category="top",
            primary_color="blue",
            secondary_colors=["white"],
            pattern="striped",
            style_tags=["smart_casual"],
        ).id,
        "jeans": g.add("Blue jeans", category="bottom", primary_color="blue").id,
        "shoes": g.add(
            "100% leather shoes", category="footwear", availability_status="unavailable"
        ).id,
    }


def _names(items: list[object]) -> set[str]:
    return {i.display_name for i in items}  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("flt", "expected"),
    [
        (GarmentFilter(category="top"), {"White T-shirt", "Striped shirt"}),
        (GarmentFilter(color="blue"), {"Striped shirt", "Blue jeans"}),
        (GarmentFilter(color="white"), {"White T-shirt", "Striped shirt"}),  # primary or secondary
        (GarmentFilter(style="casual"), {"White T-shirt"}),  # exact tag, not substring
        (GarmentFilter(tag="summer"), {"White T-shirt"}),
        (GarmentFilter(pattern="striped"), {"Striped shirt"}),
        (GarmentFilter(availability="unavailable"), {"100% leather shoes"}),
        (GarmentFilter(q="jean"), {"Blue jeans"}),
        (GarmentFilter(q="100%"), {"100% leather shoes"}),  # LIKE wildcard is escaped
        (GarmentFilter(q="%"), {"100% leather shoes"}),
        (GarmentFilter(category="top", color="blue"), {"Striped shirt"}),
    ],
)
def test_list_filters(engine: Engine, flt: GarmentFilter, expected: set[str]) -> None:
    with UnitOfWork(engine) as uow:
        _seed(uow)
    with UnitOfWork(engine) as uow:
        items, total = uow.garments.list(flt)
    assert _names(list(items)) == expected and total == len(expected)


def test_list_processing_status_filter(engine: Engine) -> None:
    with UnitOfWork(engine) as uow:
        ids = _seed(uow)
        uow.session.add(Processing(id="p1", garment_id=ids["tee"], status="needs_review"))
        uow.session.add(Processing(id="p2", garment_id=ids["jeans"], status="ready"))
    with UnitOfWork(engine) as uow:
        items, _ = uow.garments.list(GarmentFilter(processing_status="needs_review"))
    assert _names(list(items)) == {"White T-shirt"}


def test_list_pagination_reports_total(engine: Engine) -> None:
    with UnitOfWork(engine) as uow:
        _seed(uow)
    with UnitOfWork(engine) as uow:
        first, total = uow.garments.list(limit=3)
        rest, total2 = uow.garments.list(limit=3, offset=3)
    assert (len(first), len(rest), total, total2) == (3, 1, 4, 4)
    assert not {g.id for g in first} & {g.id for g in rest}


def test_update_sets_fields_clears_and_touches_updated_at(engine: Engine) -> None:
    with UnitOfWork(engine) as uow:
        g = uow.garments.add("Tee", category="top", pattern="solid")
        gid, created = g.id, g.updated_at
    time.sleep(0.01)
    with UnitOfWork(engine) as uow:
        g = uow.garments.update(gid, primary_color="red", pattern=None)  # type: ignore[assignment]
        assert g.primary_color == "red" and g.pattern is None and g.updated_at > created
        assert uow.garments.update("nope", pattern="x") is None
        with pytest.raises(ValueError):
            uow.garments.update(gid, deleted_at="x")  # not editable through update()


def test_soft_delete_hides_garment(engine: Engine) -> None:
    with UnitOfWork(engine) as uow:
        gid = uow.garments.add("Old tee").id
    with UnitOfWork(engine) as uow:
        assert uow.garments.soft_delete(gid) is True
        assert uow.garments.soft_delete(gid) is False  # already gone
    with UnitOfWork(engine) as uow:
        assert uow.garments.get(gid) is None
        assert uow.garments.get(gid, include_deleted=True) is not None
        assert uow.garments.list()[1] == 0
        assert uow.garments.update(gid, pattern="x") is None


# --- other repositories (T3) ----------------------------------------------------------------


def test_evidence_history_and_latest(engine: Engine) -> None:
    with UnitOfWork(engine) as uow:
        gid = uow.garments.add("Tee").id
        uow.evidence.add(gid, "color", "red", "model", confidence=0.6, model_version="clip-1")
        uow.evidence.add(gid, "color", "maroon", "user", confirmed_at="2026-01-01T00:00:00Z")
        uow.evidence.add(gid, "pattern", None, "model")  # unknown stays NULL
    with UnitOfWork(engine) as uow:
        assert len(uow.evidence.list_for_garment(gid)) == 3
        latest = uow.evidence.latest(gid, "color")
        assert latest is not None and latest.value == "maroon"
        model = uow.evidence.latest(gid, "color", source="model")
        assert model is not None and model.confidence == 0.6
        pattern = uow.evidence.latest(gid, "pattern")
        assert pattern is not None and pattern.value is None
        assert uow.evidence.latest(gid, "style") is None


def test_outfit_create_items_flags_and_lists(engine: Engine) -> None:
    with UnitOfWork(engine) as uow:
        top = uow.garments.add("Tee").id
        bottom = uow.garments.add("Jeans").id
        oid = uow.outfits.create(
            [(top, "top"), (bottom, "bottom")],
            style_label="casual",
            score_out_of_10=7.5,
            score_factors={"color": 0.8},
            brief_snapshot={"occasion": "dinner"},
        ).id
        uow.outfits.create([(top, "top")])
    with UnitOfWork(engine) as uow:
        assert [(i.garment_id, i.role) for i in uow.outfits.items(oid)] == [
            (top, "top"),
            (bottom, "bottom"),
        ]
        assert uow.outfits.set_saved(oid, True) and uow.outfits.set_favorite(oid, True)
        assert not uow.outfits.set_favorite("nope", True)
    with UnitOfWork(engine) as uow:
        assert [o.id for o in uow.outfits.list(saved=True)] == [oid]
        assert [o.id for o in uow.outfits.list(favorite=True)] == [oid]
        assert len(uow.outfits.list()) == 2
        o = uow.outfits.get(oid)
        assert o is not None and o.score_factors == {"color": 0.8} and o.score_out_of_10 == 7.5
        assert uow.outfits.set_favorite(oid, False)
    with UnitOfWork(engine) as uow:
        assert uow.outfits.list(favorite=True) == []


def test_feedback_usage_and_preferences(engine: Engine) -> None:
    with UnitOfWork(engine) as uow:
        gid = uow.garments.add("Tee").id
        oid = uow.outfits.create([(gid, "top")]).id
        uow.feedback.add(oid, "like")
        uow.feedback.add(oid, "worn", reason="dinner")
        uow.usage.add(gid, "worn", oid)
        uow.preferences.set("style", "understated", 0.5)
    with UnitOfWork(engine) as uow:
        assert [f.action for f in uow.feedback.list_for_outfit(oid)] == ["like", "worn"]
        events = uow.usage.list_for_garment(gid)
        assert [(e.event_type, e.outfit_id) for e in events] == [("worn", oid)]
        uow.preferences.set("style", "bold")  # upsert
        uow.preferences.set("palette", "neutral")
    with UnitOfWork(engine) as uow:
        pref = uow.preferences.get("style")
        assert pref is not None and pref.value == "bold" and pref.weight is None
        assert [p.key for p in uow.preferences.all()] == ["palette", "style"]


# --- layering (acceptance criterion) --------------------------------------------------------


def test_model_code_does_not_import_repository() -> None:
    app_dir = Path(__file__).resolve().parents[1] / "app"
    pattern = re.compile(r"^\s*(from|import)\s+app\.repository", re.MULTILINE)
    for package in ("llm", "vision"):
        for py in (app_dir / package).rglob("*.py"):
            assert not pattern.search(py.read_text(encoding="utf-8")), py
