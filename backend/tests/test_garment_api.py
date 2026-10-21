"""Tests for the garment browse / detail / edit / delete API (BE-E1-S5)."""

import io
import statistics
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repository.models import Processing
from app.repository.unit_of_work import UnitOfWork


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A started test client (database migrated, storage ready)."""
    with TestClient(create_app()) as c:
        yield c


def _uow(client: TestClient) -> UnitOfWork:
    """Open a unit of work on the test app's database."""
    return UnitOfWork(client.app.state.engine)  # type: ignore[attr-defined]


def _seed(client: TestClient) -> dict[str, str]:
    """Insert four garments and return their ids by short name."""
    with _uow(client) as uow:
        g = uow.garments
        ids = {
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
            ).id,
            "jeans": g.add("Blue jeans", category="bottom", primary_color="blue").id,
            "shoes": g.add("Old shoes", category="footwear", availability_status="unavailable").id,
        }
        uow.session.add(Processing(id="p1", garment_id=ids["tee"], status="needs_review"))
        uow.session.add(Processing(id="p2", garment_id=ids["jeans"], status="ready"))
    return ids


# --- list (T2) ------------------------------------------------------------------------------


def test_list_returns_page_shape(client: TestClient) -> None:
    """The list response has items, total, limit and offset, and exposes processing status."""
    _seed(client)
    body = client.get("/api/garments", params={"limit": 3}).json()
    assert (body["total"], body["limit"], body["offset"], len(body["items"])) == (4, 3, 0, 3)
    by_name = {i["display_name"]: i for i in body["items"]}
    assert "thumbnail_url" in next(iter(by_name.values()))
    page2 = client.get("/api/garments", params={"limit": 3, "offset": 3}).json()
    assert len(page2["items"]) == 1


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"category": "top"}, {"White T-shirt", "Striped shirt"}),
        ({"color": "white"}, {"White T-shirt", "Striped shirt"}),
        ({"style": "casual"}, {"White T-shirt"}),
        ({"tag": "summer"}, {"White T-shirt"}),
        ({"pattern": "striped"}, {"Striped shirt"}),
        ({"availability": "unavailable"}, {"Old shoes"}),
        ({"status": "needs_review"}, {"White T-shirt"}),
        ({"q": "jean"}, {"Blue jeans"}),
        ({"category": "top", "color": "blue"}, {"Striped shirt"}),
    ],
)
def test_list_filters(client: TestClient, params: dict[str, str], expected: set[str]) -> None:
    """Each query parameter filters the list as documented; filters combine with AND."""
    _seed(client)
    items = client.get("/api/garments", params=params).json()["items"]
    assert {i["display_name"] for i in items} == expected


def test_list_includes_thumbnail_url_and_processing_status(client: TestClient) -> None:
    """A garment with a thumbnail shows its URL, one without shows null."""
    ids = _seed(client)
    storage = client.app.state.storage  # type: ignore[attr-defined]
    with _uow(client) as uow:
        thumb = storage.save(io.BytesIO(b"t"), "t.jpg", kind="thumbnails")
        uow.garments.add_image(ids["tee"], "originals/x.jpg", "image/jpeg", 1, thumb)
    items = {i["id"]: i for i in client.get("/api/garments").json()["items"]}
    assert items[ids["tee"]]["thumbnail_url"] == f"/api/garments/{ids['tee']}/thumbnail"
    assert items[ids["tee"]]["processing_status"] == "needs_review"
    assert items[ids["jeans"]]["thumbnail_url"] is None


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
def test_list_rejects_bad_paging(client: TestClient, params: dict[str, int]) -> None:
    """Out-of-range limit/offset values return 422."""
    assert client.get("/api/garments", params=params).status_code == 422


# --- detail (T3) ----------------------------------------------------------------------------


def test_detail_has_images_processing_and_provenance(client: TestClient) -> None:
    """Detail shows images, the processing record and per-attribute provenance."""
    ids = _seed(client)
    with _uow(client) as uow:
        uow.garments.add_image(ids["tee"], "originals/x.jpg", "image/jpeg", 123, "thumbnails/y.jpg")
        uow.evidence.add(ids["tee"], "category", "top", "model", confidence=0.9, model_version="m1")
        uow.evidence.add(ids["tee"], "pattern", "dotted", "model", confidence=0.4)
        uow.evidence.add(ids["tee"], "pattern", "solid", "user", confirmed_at="2026-01-01")
    d = client.get(f"/api/garments/{ids['tee']}").json()
    assert d["images"][0]["image_url"] == f"/api/garments/{ids['tee']}/image"
    assert d["images"][0]["file_size"] == 123
    assert d["processing"]["status"] == "needs_review"
    cat, pat, color = (d["attributes"][k] for k in ("category", "pattern", "primary_color"))
    assert (cat["source"], cat["confidence"], cat["model_version"], cat["confirmed"]) == (
        "model",
        0.9,
        "m1",
        False,
    )
    assert (pat["source"], pat["value"], pat["confirmed"]) == ("user", "solid", True)  # user wins
    assert (color["source"], color["value"], color["confirmed"]) == (None, "white", False)


def test_detail_404_for_unknown_and_deleted(client: TestClient) -> None:
    """Unknown ids and soft-deleted garments return 404."""
    ids = _seed(client)
    assert client.get("/api/garments/nope").status_code == 404
    assert client.delete(f"/api/garments/{ids['tee']}").status_code == 204
    assert client.get(f"/api/garments/{ids['tee']}").status_code == 404


# --- update (T4) ----------------------------------------------------------------------------


def test_patch_updates_and_records_user_evidence(client: TestClient) -> None:
    """PATCH changes fields, stores user-confirmed evidence and returns the new detail."""
    ids = _seed(client)
    r = client.patch(
        f"/api/garments/{ids['tee']}",
        json={"primary_color": "cream", "style_tags": ["minimal"], "display_name": "Ivory tee"},
    )
    assert r.status_code == 200
    d = r.json()
    assert (d["display_name"], d["primary_color"], d["style_tags"]) == (
        "Ivory tee",
        "cream",
        ["minimal"],
    )
    color = d["attributes"]["primary_color"]
    assert (color["source"], color["confirmed"], color["value"]) == ("user", True, "cream")
    assert color["confirmed_at"] is not None
    # display_name is not an AI attribute, so it gets no evidence row.
    with _uow(client) as uow:
        names = {e.attribute_name for e in uow.evidence.list_for_garment(ids["tee"])}
    assert names == {"primary_color", "style_tags"}


def test_patch_null_clears_attribute_and_confirms_it(client: TestClient) -> None:
    """Sending null clears an AI attribute; the empty value is itself user-confirmed."""
    ids = _seed(client)
    d = client.patch(f"/api/garments/{ids['tee']}", json={"pattern": None}).json()
    assert d["pattern"] is None
    assert d["attributes"]["pattern"]["confirmed"] is True


def test_patch_same_value_still_confirms(client: TestClient) -> None:
    """Re-sending the current value records a confirmation ("looks right")."""
    ids = _seed(client)
    d = client.patch(f"/api/garments/{ids['tee']}", json={"category": "top"}).json()
    assert d["attributes"]["category"]["confirmed"] is True


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"display_name": None},
        {"availability_status": None},
        {"availability_status": "lost"},
        {"formality": 9},
        {"formality": "very"},
        {"style_tags": ["ok", ""]},
        {"style_tags": ["x"] * 21},
        {"category": "x" * 101},
        {"deleted_at": "2020-01-01"},
        {"id": "other"},
    ],
)
def test_patch_validation_rejects_bad_bodies(client: TestClient, body: dict[str, Any]) -> None:
    """Empty bodies, bad enums/ranges/sizes, non-clearable nulls and unknown fields give 422."""
    ids = _seed(client)
    assert client.patch(f"/api/garments/{ids['tee']}", json=body).status_code == 422


def test_patch_unknown_garment_404_and_nothing_written(client: TestClient) -> None:
    """Patching a missing or deleted garment returns 404 and writes no evidence."""
    ids = _seed(client)
    assert client.patch("/api/garments/nope", json={"pattern": "x"}).status_code == 404
    client.delete(f"/api/garments/{ids['tee']}")
    assert client.patch(f"/api/garments/{ids['tee']}", json={"pattern": "x"}).status_code == 404
    with _uow(client) as uow:
        assert uow.evidence.list_for_garment(ids["tee"]) == []


def test_patch_availability_makes_garment_filterable(client: TestClient) -> None:
    """Marking a garment unavailable shows up in the availability filter."""
    ids = _seed(client)
    client.patch(f"/api/garments/{ids['tee']}", json={"availability_status": "unavailable"})
    items = client.get("/api/garments", params={"availability": "unavailable"}).json()["items"]
    assert {i["display_name"] for i in items} == {"Old shoes", "White T-shirt"}


# --- delete (T5) ----------------------------------------------------------------------------


def test_delete_is_soft_and_keeps_files(client: TestClient) -> None:
    """DELETE hides the garment but keeps its row, evidence and image file."""
    ids = _seed(client)
    storage = client.app.state.storage  # type: ignore[attr-defined]
    with _uow(client) as uow:
        rel = storage.save(io.BytesIO(b"keep"), "a.jpg")
        uow.garments.add_image(ids["tee"], rel, "image/jpeg", 4)
    assert client.delete(f"/api/garments/{ids['tee']}").status_code == 204
    assert client.delete(f"/api/garments/{ids['tee']}").status_code == 404  # already gone
    assert client.get("/api/garments").json()["total"] == 3
    assert storage.resolve(rel).read_bytes() == b"keep"
    with _uow(client) as uow:
        assert uow.garments.get(ids["tee"], include_deleted=True) is not None


# --- performance (T6) -----------------------------------------------------------------------


def test_list_latency_on_500_garments(client: TestClient) -> None:
    """List/filter requests stay well under 1 second (p95) on a 500-garment wardrobe (NFR-004)."""
    cats = ["top", "bottom", "footwear", "layer", "ethnic"]
    colors = ["white", "black", "blue", "red", "beige"]
    styles = ["casual", "formal", "classic", "bold"]
    with _uow(client) as uow:
        for i in range(500):
            uow.garments.add(
                f"Garment {i}",
                category=cats[i % 5],
                primary_color=colors[i % 5],
                secondary_colors=[colors[(i + 1) % 5]],
                style_tags=[styles[i % 4]],
                season_tags=["summer"],
                pattern="solid",
            )
    queries: list[dict[str, Any]] = [
        {},
        {"category": "top"},
        {"color": "blue"},  # primary or secondary (JSON scan)
        {"style": "casual"},  # JSON scan
        {"tag": "summer", "limit": 200},
        {"q": "Garment 4"},
        {"category": "top", "style": "formal", "color": "white"},
    ]
    timings: list[float] = []
    for _ in range(8):
        for params in queries:
            start = time.perf_counter()
            r = client.get("/api/garments", params=params)
            timings.append(time.perf_counter() - start)
            assert r.status_code == 200
    timings.sort()
    p95 = timings[int(len(timings) * 0.95) - 1]
    print(
        f"list latency, {len(timings)} calls: "
        f"median={statistics.median(timings):.4f}s p95={p95:.4f}s"
    )
    assert p95 < 1.0


# --- persistence (T7) -----------------------------------------------------------------------


def test_data_survives_app_restart() -> None:
    """Garments and user edits are still there after the app is shut down and started again."""
    with TestClient(create_app()) as first:
        ids = _seed(first)
        first.patch(f"/api/garments/{ids['tee']}", json={"primary_color": "cream"})
        first.delete(f"/api/garments/{ids['jeans']}")
    with TestClient(create_app()) as second:  # same data dir, fresh app and engine
        body = second.get("/api/garments").json()
        assert body["total"] == 3
        d = second.get(f"/api/garments/{ids['tee']}").json()
        assert d["primary_color"] == "cream" and d["attributes"]["primary_color"]["confirmed"]
        assert second.get(f"/api/garments/{ids['jeans']}").status_code == 404
