from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import get_settings
from app.domain.taxonomy import get_taxonomy


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("WARDROBE_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_taxonomy.cache_clear()
    yield
    get_settings.cache_clear()
    get_taxonomy.cache_clear()
