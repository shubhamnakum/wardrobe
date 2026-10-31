"""Tests for the taxonomy (BE-E1-S6): loading, validation, cleaning AI output and the API."""

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.domain.taxonomy import (
    DEFAULT_TAXONOMY_PATH,
    Taxonomy,
    TaxonomyError,
    get_taxonomy,
    load_taxonomy,
)
from app.main import create_app
from app.repository.db import MIGRATIONS_DIR, make_engine, migrate
from app.repository.unit_of_work import UnitOfWork


@pytest.fixture
def tax() -> Taxonomy:
    """The packaged taxonomy."""
    return load_taxonomy(DEFAULT_TAXONOMY_PATH)


@pytest.fixture
def raw() -> dict[str, Any]:
    """The packaged taxonomy file as a plain dict (to build broken variants from)."""
    return json.loads(DEFAULT_TAXONOMY_PATH.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A started test client."""
    with TestClient(create_app()) as c:
        yield c


# --- the packaged file (T1, T2) --------------------------------------------------------------


def test_packaged_taxonomy_loads_and_covers_the_agreed_details(tax: Taxonomy) -> None:
    """The file is valid and defines the detail attributes agreed for tops, bottoms, footwear,
    dresses and traditional wear."""

    def keys(name: str) -> set[str]:
        category = tax.category(name)
        assert category is not None
        return set(category.details)

    assert tax.version >= 1
    assert keys("top") >= {"collar", "sleeve_length", "closure", "fit"}
    assert keys("bottom") >= {"fit", "rise", "length", "closure"}
    assert keys("footwear") >= {"closure", "heel", "toe"}
    assert keys("dress") >= {"neckline", "sleeve_length", "length", "silhouette"}
    assert keys("ethnic") >= {"neckline", "sleeve_length", "length", "silhouette"}
    assert {"ethnic", "dress", "set", "activewear", "accessory"} <= {c.name for c in tax.categories}


def _write(tmp_path: Path, data: dict[str, Any]) -> Path:
    """Write a taxonomy dict to a temp file and return its path."""
    path = tmp_path / "t.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _mutations(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Broken variants of the packaged file, one defect each."""
    out = []
    for change in (
        lambda d: d["patterns"].append("solid"),  # duplicate
        lambda d: d["patterns"].append("Not Snake"),  # bad name
        lambda d: d["colors"][0].update(hex="red"),  # bad hex
        lambda d: d["formality"]["labels"].pop("3"),  # gap in labels
        lambda d: d["formality"].update(min=5, max=1),  # reversed scale
        lambda d: d.update(version=0),  # bad version
        lambda d: d["seasons"].clear(),  # empty list
        lambda d: d["categories"][0]["details"].update(collar=[]),  # empty detail values
        lambda d: d["categories"].append(copy.deepcopy(d["categories"][0])),  # duplicate category
        lambda d: d.pop("colors"),  # missing section
    ):
        data = copy.deepcopy(raw)
        change(data)
        out.append(data)
    return out


def test_broken_taxonomy_files_are_rejected(raw: dict[str, Any], tmp_path: Path) -> None:
    """Every kind of defect in the file is caught at load time, naming the file."""
    for broken in _mutations(raw):
        path = _write(tmp_path, broken)
        with pytest.raises(ValueError, match="Invalid taxonomy file"):
            load_taxonomy(path)


def test_missing_or_unparseable_file_is_rejected(tmp_path: Path) -> None:
    """A missing file or invalid JSON raises a clear error."""
    with pytest.raises(ValueError, match="Invalid taxonomy file"):
        load_taxonomy(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid taxonomy file"):
        load_taxonomy(bad)


def test_taxonomy_path_can_be_overridden_in_settings(
    raw: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WARDROBE_TAXONOMY_PATH points the app at a different (valid) file."""
    raw["version"] = 99
    monkeypatch.setenv("WARDROBE_TAXONOMY_PATH", str(_write(tmp_path, raw)))
    get_settings.cache_clear()
    get_taxonomy.cache_clear()
    try:
        assert get_taxonomy().version == 99
    finally:
        get_taxonomy.cache_clear()


# --- endpoint (T3) ---------------------------------------------------------------------------


def test_taxonomy_endpoint(client: TestClient) -> None:
    """GET /api/taxonomy returns every list the UI needs for its dropdowns."""
    body = client.get("/api/taxonomy").json()
    assert body["version"] >= 1
    assert {"version", "formality", "layering_roles", "seasons", "style_tags", "patterns"} <= set(
        body
    )
    assert body["formality"]["labels"]["5"] == "Formal"
    assert all(c["hex"].startswith("#") for c in body["colors"])
    top = next(c for c in body["categories"] if c["name"] == "top")
    assert "t_shirt" in top["subcategories"] and "mandarin" in top["details"]["collar"]


# --- validation of writes (T8) ---------------------------------------------------------------


@pytest.mark.parametrize(
    "fields",
    [
        {"category": "hat"},
        # open fields: bad format (not lower_snake_case) still rejected
        {"primary_color": "Ivory White"},
        {"secondary_colors": ["white", "Ivory White"]},
        {"pattern": "Very Spotty!"},
        {"style_tags": ["casual", "Wacky Style"]},
        # closed fields: any unknown value rejected
        {"season_tags": ["fall"]},
        {"layering_role": "top"},
        {"formality": 0},
        {"formality": 6},
        {"formality": True},
        {"category": "top", "subcategory": "jeans"},  # subcategory from another category
        {"subcategory": "t_shirt"},  # subcategory without a category
        {"details": {"collar": "mandarin"}},  # details without a category
        {"category": "top", "details": {"rise": "high"}},  # key not defined for top
        {"category": "top", "details": {"collar": "spaceship"}},  # value not allowed
    ],
)
def test_validate_rejects_values_outside_taxonomy(tax: Taxonomy, fields: dict[str, Any]) -> None:
    """Each kind of invalid value raises a TaxonomyError.

    Open fields (colors, pattern, style_tags) accept custom lower_snake_case values but still
    reject badly-formatted strings (spaces, capitals, special characters).
    """
    with pytest.raises(TaxonomyError):
        tax.validate_fields(fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"primary_color": "coral_peach"},                    # custom color not in palette
        {"secondary_colors": ["white", "earthy_rust"]},      # mix curated + custom
        {"pattern": "cotton_linen"},                         # custom texture pattern
        {"style_tags": ["casual", "dopamine_dressing"]},     # curated + custom tag
    ],
)
def test_validate_accepts_custom_values_for_open_fields(
    tax: Taxonomy, fields: dict[str, Any]
) -> None:
    """Open fields (colors, pattern, style_tags) accept user-defined lower_snake_case values
    that are not in the curated list. The taxonomy list is treated as suggestions for humans,
    not a hard constraint. AI output is still sanitized strictly.
    """
    tax.validate_fields(fields)  # must not raise


def test_validate_accepts_valid_and_null_values(tax: Taxonomy) -> None:
    """A fully valid write passes, and None (clearing) is always allowed."""
    tax.validate_fields(
        {
            "category": "top",
            "subcategory": "shirt",
            "primary_color": "navy",
            "secondary_colors": ["white"],
            "pattern": "striped",
            "formality": 3,
            "style_tags": ["smart_casual"],
            "season_tags": ["all_season"],
            "layering_role": "base",
            "details": {"collar": "button_down", "closure": "buttons"},
        }
    )
    tax.validate_fields({"category": None, "pattern": None, "formality": None, "details": None})


def test_validate_reports_every_problem(tax: Taxonomy) -> None:
    """All errors are collected, not just the first.

    Uses two closed-field errors (category, season_tag) plus one formality error so the
    count is predictable regardless of open-field behaviour.
    """
    with pytest.raises(TaxonomyError) as exc:
        tax.validate_fields({"category": "hat", "season_tags": ["fall"], "formality": 9})
    assert len(exc.value.errors) == 3


def test_validate_uses_current_values_for_pairs(tax: Taxonomy) -> None:
    """Changing only the category fails if the existing subcategory/details no longer fit."""
    current = {"category": "top", "subcategory": "shirt", "details": {"collar": "spread"}}
    with pytest.raises(TaxonomyError) as exc:
        tax.validate_fields({"category": "bottom"}, current)
    assert any(e.startswith("subcategory") for e in exc.value.errors)
    assert any(e.startswith("details.collar") for e in exc.value.errors)
    tax.validate_fields({"category": "top", "pattern": "solid"}, current)  # unchanged pair is fine


# --- cleaning AI output (T9) -----------------------------------------------------------------


def test_sanitize_nulls_values_outside_taxonomy(tax: Taxonomy) -> None:
    """Model output outside the lists becomes None (or is dropped from lists) and never raises."""
    cleaned = tax.sanitize(
        {
            "category": "top",
            "subcategory": "jeans",  # wrong category
            "primary_color": "ivory",
            "secondary_colors": ["white", "ivory"],
            "pattern": "spotty",
            "formality": 7,
            "style_tags": ["wacky"],
            "season_tags": "summer",  # wrong type
            "layering_role": "base",
            "details": {"collar": "mandarin", "rise": "high", "fit": "tight"},
        }
    )
    assert cleaned == {
        "category": "top",
        "subcategory": None,
        "primary_color": None,
        "secondary_colors": ["white"],
        "pattern": None,
        "formality": None,
        "style_tags": None,
        "season_tags": None,
        "layering_role": "base",
        "details": {"collar": "mandarin"},
    }


def test_sanitize_drops_subcategory_and_details_when_category_is_invalid(tax: Taxonomy) -> None:
    """Without a valid category there is nothing for subcategory/details to belong to."""
    cleaned = tax.sanitize(
        {"category": "hat", "subcategory": "cap", "details": {"collar": "mandarin"}}
    )
    assert cleaned == {"category": None, "subcategory": None, "details": None}


def test_sanitize_only_returns_given_keys(tax: Taxonomy) -> None:
    """Keys that were not predicted are not invented."""
    assert tax.sanitize({"pattern": "solid"}) == {"pattern": "solid"}


# --- details merging -------------------------------------------------------------------------


def test_merge_details_sets_clears_and_prunes(tax: Taxonomy) -> None:
    """Merge sets keys, removes None keys, and drops details that do not fit the category."""
    base = {"collar": "spread", "fit": "slim"}
    assert tax.merge_details("top", base, {"collar": "mandarin"}) == {
        "collar": "mandarin",
        "fit": "slim",
    }
    assert tax.merge_details("top", base, {"fit": None}) == {"collar": "spread"}
    assert tax.merge_details("top", {"fit": "slim"}, {"fit": None}) is None  # nothing left
    assert tax.merge_details("bottom", base, {}) == {"fit": "slim"}  # collar is not a bottom detail
    assert tax.merge_details(None, base, {}) is None


# --- API behaviour (T8, T10) -----------------------------------------------------------------


def _garment(client: TestClient, **fields: Any) -> str:
    """Create a garment directly in the database and return its id."""
    with UnitOfWork(client.app.state.engine) as uow:  # type: ignore[attr-defined]
        return uow.garments.add("Test garment", **fields).id


def test_repository_rejects_invalid_values_on_add(client: TestClient) -> None:
    """Writes outside the taxonomy are rejected at the repository, whatever the caller."""
    with pytest.raises(TaxonomyError), UnitOfWork(client.app.state.engine) as uow:  # type: ignore[attr-defined]
        uow.garments.add("Bad", category="hat")


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"category": "hat"}, ["body", "category"]),
        # primary_color with bad format (open field, but must be lower_snake_case)
        ({"primary_color": "Ivory White"}, ["body", "primary_color"]),
        ({"details": {"collar": "mandarin"}}, ["body", "details"]),  # garment has no category
        ({"subcategory": "t_shirt"}, ["body", "subcategory"]),
    ],
)
def test_patch_outside_taxonomy_is_422_in_fastapi_shape(
    client: TestClient, body: dict[str, Any], field: list[str]
) -> None:
    """Taxonomy errors use the same {"detail": [{"loc", "msg"}]} shape as other 422s.

    Open fields (colors, pattern, style_tags) are still 422 when the value is not
    lower_snake_case (e.g. has spaces or capitals).
    """
    gid = _garment(client)
    r = client.patch(f"/api/garments/{gid}", json=body)
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == field and r.json()["detail"][0]["msg"]


def test_patch_details_saved_with_per_key_evidence_and_provenance(client: TestClient) -> None:
    """Details are merged, each key gets its own user evidence, and provenance lists them."""
    gid = _garment(client, category="top", details={"fit": "slim"})
    r = client.patch(
        f"/api/garments/{gid}", json={"details": {"collar": "mandarin", "closure": "buttons"}}
    )
    assert r.status_code == 200
    d = r.json()
    assert d["details"] == {"fit": "slim", "collar": "mandarin", "closure": "buttons"}
    collar = d["attributes"]["details.collar"]
    assert (collar["value"], collar["source"], collar["confirmed"]) == ("mandarin", "user", True)
    assert d["attributes"]["details.fit"]["source"] is None  # existing, never confirmed
    with UnitOfWork(client.app.state.engine) as uow:  # type: ignore[attr-defined]
        names = {e.attribute_name for e in uow.evidence.list_for_garment(gid)}
    assert names == {"details.collar", "details.closure"}


def test_patch_details_key_null_removes_it(client: TestClient) -> None:
    """A detail set to null is removed and the removal is recorded as confirmed."""
    gid = _garment(client, category="top", details={"fit": "slim", "collar": "spread"})
    d = client.patch(f"/api/garments/{gid}", json={"details": {"fit": None}}).json()
    assert d["details"] == {"collar": "spread"}
    assert d["attributes"]["details.fit"]["confirmed"] is True
    assert d["attributes"]["details.fit"]["value"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"details": None},
        {"details": {"": "x"}},
        {"details": {"collar": ""}},
        {"details": {"collar": "spaceship"}},
        {"details": {"rise": "high"}},
    ],
)
def test_patch_bad_details_is_422(client: TestClient, body: dict[str, Any]) -> None:
    """Null details, empty keys/values, values outside the taxonomy and keys that do not exist
    for the category are rejected."""
    gid = _garment(client, category="top")
    assert client.patch(f"/api/garments/{gid}", json=body).status_code == 422


def test_changing_category_prunes_details_that_no_longer_fit(client: TestClient) -> None:
    """Moving a garment to another category keeps valid details and drops the rest."""
    gid = _garment(client, category="top", details={"collar": "spread", "fit": "slim"})
    d = client.patch(f"/api/garments/{gid}", json={"category": "bottom"}).json()
    assert d["category"] == "bottom" and d["details"] == {"fit": "slim"}


def test_changing_category_with_stale_subcategory_is_422_and_changes_nothing(
    client: TestClient,
) -> None:
    """The user must change the subcategory together with the category."""
    gid = _garment(client, category="top", subcategory="shirt")
    assert client.patch(f"/api/garments/{gid}", json={"category": "bottom"}).status_code == 422
    assert client.get(f"/api/garments/{gid}").json()["category"] == "top"
    both = {"category": "bottom", "subcategory": "jeans"}
    assert client.patch(f"/api/garments/{gid}", json=both).status_code == 200


def test_list_and_detail_expose_details(client: TestClient) -> None:
    """Details appear in the list items and the detail view."""
    gid = _garment(client, category="footwear", details={"closure": "laces", "toe": "round"})
    item = client.get("/api/garments").json()["items"][0]
    assert item["details"] == {"closure": "laces", "toe": "round"}
    assert client.get(f"/api/garments/{gid}").json()["details"] == item["details"]


# --- migration 002 (T6) ----------------------------------------------------------------------


def test_details_column_rejects_invalid_json(tmp_path: Path) -> None:
    """The database itself refuses non-JSON text in garment.details."""
    engine = make_engine(tmp_path / "m.db")
    migrate(engine)
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text("INSERT INTO garment (id, display_name, details) VALUES ('g','x','nope')"))
    engine.dispose()


def test_migrations_upgrade_downgrade_upgrade(tmp_path: Path) -> None:
    """Migration 002 can be rolled back and re-applied without error."""
    engine = make_engine(tmp_path / "m.db")
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    for target, action in (
        ("head", command.upgrade),
        ("001", command.downgrade),
        ("head", command.upgrade),
    ):
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            action(cfg, target)
    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(garment)"))}
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert "details" in columns and version == "002"
    engine.dispose()
