"""Tests for the local file storage service and the image-serving endpoints (BE-E1-S4)."""

import io
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repository.unit_of_work import UnitOfWork
from app.storage import InvalidStoragePath, StorageService
from app.storage.service import normalize_filename, safe_extension


@pytest.fixture
def storage(tmp_path: Path) -> StorageService:
    """A storage service rooted in a fresh temp folder."""
    return StorageService(tmp_path / "store")


# --- naming and saving (T1, T2) -------------------------------------------------------------


def test_creates_root_and_subfolders(storage: StorageService) -> None:
    """The root and the originals/thumbnails sub-folders exist after construction."""
    assert (storage.root / "originals").is_dir() and (storage.root / "thumbnails").is_dir()


def test_save_uses_server_generated_name(storage: StorageService) -> None:
    """The stored name is a random hex id; the client file name never appears on disk."""
    rel = storage.save(io.BytesIO(b"data"), "My Holiday Photo.JPG")
    assert rel.startswith("originals/") and rel.endswith(".jpg")
    assert "holiday" not in rel.lower()
    assert storage.resolve(rel).read_bytes() == b"data"
    assert storage.save(io.BytesIO(b"x"), "My Holiday Photo.JPG") != rel  # unique each time


def test_save_thumbnail_kind(storage: StorageService) -> None:
    """Thumbnails go to the thumbnails folder."""
    assert storage.save(io.BytesIO(b"t"), "a.png", kind="thumbnails").startswith("thumbnails/")


@pytest.mark.parametrize(
    "hostile",
    [
        "../../evil.png",
        "..\\..\\evil.png",
        "C:\\Windows\\win.ini",
        "/etc/passwd",
        "a/b/c.jpg",
        "shell.php",
        "x.php.jpg",
        "",
        None,
        "con.png",
        "a" * 500 + ".png",
        "name\0.png",
    ],
)
def test_hostile_client_filenames_stay_inside_root(
    storage: StorageService, hostile: str | None
) -> None:
    """Whatever the client calls the file, it lands inside the root with a safe name."""
    rel = storage.save(io.BytesIO(b"x"), hostile)
    path = storage.resolve(rel)
    assert path.is_relative_to(storage.root) and path.parent == storage.root / "originals"
    assert path.suffix in {".jpg", ".png", ".img"}
    assert len(path.name) < 60


def test_normalize_filename_and_extension() -> None:
    """Display names lose directories and odd characters; extensions are allow-listed."""
    assert normalize_filename("../../a b.png") == "a_b.png"
    assert normalize_filename("   ") == "upload"
    assert normalize_filename(None) == "upload"
    assert safe_extension("photo.JPEG") == ".jpeg"
    assert safe_extension("run.exe") == ".img"
    assert safe_extension("noext") == ".img"


def test_failed_save_leaves_no_partial_file(storage: StorageService) -> None:
    """If reading the source fails, no file is left behind."""

    class Broken(io.RawIOBase):
        """A source that fails on first read."""

        def readable(self) -> bool:
            return True

        def read(self, size: int = -1) -> bytes:
            raise OSError("disk on fire")

    with pytest.raises(OSError):
        storage.save(Broken(), "a.jpg")  # type: ignore[arg-type]
    assert list((storage.root / "originals").iterdir()) == []


# --- path traversal (T4) --------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "../x",
        "..\\x",
        "originals/../../x",
        "originals/..\\..\\x",
        "/etc/passwd",
        "\\Windows\\win.ini",
        "C:\\Windows\\win.ini",
        "C:win.ini",
        "//server/share/x",
        "originals/file.jpg:stream",
        "a\0b",
    ],
)
def test_resolve_rejects_paths_outside_root(storage: StorageService, bad: str) -> None:
    """Empty, parent-relative, absolute, drive, stream and NUL paths are all rejected."""
    with pytest.raises(InvalidStoragePath):
        storage.resolve(bad)


def test_resolve_rejects_symlink_escape(storage: StorageService, tmp_path: Path) -> None:
    """A symlink inside the root that points outside is rejected after resolving."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    link = storage.root / "originals" / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        # Windows without symlink rights: a directory junction needs no privileges and
        # resolves the same way.
        made = (
            os.name == "nt"
            and subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True
            ).returncode
            == 0
        )
        if not made:
            pytest.skip("cannot create a symlink or junction on this machine")
    with pytest.raises(InvalidStoragePath):
        storage.resolve("originals/link/secret.txt")


def test_open_and_delete(storage: StorageService) -> None:
    """Open reads what was saved; delete removes it once and then reports False."""
    rel = storage.save(io.BytesIO(b"abc"), "a.png")
    with storage.open(rel) as f:
        assert f.read() == b"abc"
    assert storage.delete(rel) is True
    assert storage.delete(rel) is False
    with pytest.raises(FileNotFoundError):
        storage.open(rel)


def test_delete_outside_root_is_rejected(storage: StorageService, tmp_path: Path) -> None:
    """delete() cannot be used to remove files outside the storage root."""
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    with pytest.raises(InvalidStoragePath):
        storage.delete("../victim.txt")
    assert victim.exists()


# --- endpoints (T3) -------------------------------------------------------------------------


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A test client with the app started (database migrated, storage ready)."""
    with TestClient(create_app()) as c:
        yield c


def _add_garment(
    client: TestClient,
    *,
    original: bytes | None = b"ORIGINAL",
    thumb: bytes | None = b"THUMB",
    original_path: str | None = None,
) -> str:
    """Create a garment (and optionally an image record + files) and return its id."""
    storage: StorageService = client.app.state.storage  # type: ignore[attr-defined]
    with UnitOfWork(client.app.state.engine) as uow:  # type: ignore[attr-defined]
        gid = uow.garments.add("Tee").id
        if original is not None or original_path is not None:
            rel = original_path or storage.save(io.BytesIO(original or b""), "a.jpg")
            thumb_rel = (
                storage.save(io.BytesIO(thumb), "t.jpg", kind="thumbnails") if thumb else None
            )
            uow.garments.add_image(gid, rel, "image/jpeg", 8, thumbnail_path=thumb_rel)
    return gid


def test_serves_original_and_thumbnail(client: TestClient) -> None:
    """Both endpoints return the stored bytes with the stored content type."""
    gid = _add_garment(client)
    r = client.get(f"/api/garments/{gid}/image")
    assert (r.status_code, r.content, r.headers["content-type"]) == (200, b"ORIGINAL", "image/jpeg")
    assert r.headers["x-content-type-options"] == "nosniff"
    t = client.get(f"/api/garments/{gid}/thumbnail")
    assert (t.status_code, t.content) == (200, b"THUMB")


def test_404_for_unknown_garment(client: TestClient) -> None:
    """An id that is not in the database returns 404."""
    assert client.get("/api/garments/nope/image").status_code == 404


def test_404_when_garment_has_no_image_or_thumbnail(client: TestClient) -> None:
    """No image record, or no thumbnail path, returns 404."""
    no_image = _add_garment(client, original=None)
    assert client.get(f"/api/garments/{no_image}/image").status_code == 404
    gid = _add_garment(client, thumb=None)
    assert client.get(f"/api/garments/{gid}/image").status_code == 200
    assert client.get(f"/api/garments/{gid}/thumbnail").status_code == 404


def test_404_for_soft_deleted_garment(client: TestClient) -> None:
    """A deleted garment's files are no longer served."""
    gid = _add_garment(client)
    with UnitOfWork(client.app.state.engine) as uow:  # type: ignore[attr-defined]
        uow.garments.soft_delete(gid)
    assert client.get(f"/api/garments/{gid}/image").status_code == 404


def test_404_when_file_missing_on_disk(client: TestClient) -> None:
    """A database record whose file vanished returns 404, not a server error."""
    gid = _add_garment(client, original_path="originals/deadbeef.jpg", thumb=None)
    assert client.get(f"/api/garments/{gid}/image").status_code == 404


def test_hostile_database_path_is_never_served(client: TestClient, tmp_path: Path) -> None:
    """Even a tampered path in the database cannot make the API serve files outside storage."""
    (tmp_path / "secret.txt").write_text("TOP SECRET")
    gid = _add_garment(client, original_path="../secret.txt", thumb=None)
    r = client.get(f"/api/garments/{gid}/image")
    assert r.status_code == 404 and "SECRET" not in r.text


def test_request_path_cannot_select_files(client: TestClient) -> None:
    """Path-like garment ids are just ids that do not exist."""
    assert client.get("/api/garments/..%2F..%2Fsecret/image").status_code == 404
