import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_ok() -> None:
    assert TestClient(create_app()).get("/health").json() == {"status": "ok"}


def test_defaults_are_localhost_and_derive_from_data_dir(tmp_path: Path) -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.host == "127.0.0.1"
    assert s.db_path == tmp_path.resolve() / "wardrobe.db"
    assert s.storage_root == tmp_path.resolve() / "images"
    assert s.model_dir == tmp_path.resolve() / "models"


def test_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WARDROBE_HOST", "0.0.0.0")
    monkeypatch.setenv("WARDROBE_MODEL_DIR", str(tmp_path / "m"))
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.host == "0.0.0.0"
    assert s.model_dir == tmp_path / "m"


def test_unhandled_error_is_short_and_logged(tmp_path: Path) -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    r = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500
    assert "secret" not in r.text and "Traceback" not in r.text
    for h in logging.getLogger().handlers:
        h.flush()
    assert "secret internal detail" in (tmp_path / "logs" / "wardrobe.log").read_text()
