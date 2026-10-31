import logging
from logging.handlers import RotatingFileHandler

from app.config.settings import Settings

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(settings: Settings) -> None:
    """Log to a local rotating file plus console. Details stay local; API errors stay short."""
    assert settings.log_dir is not None
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        settings.log_dir / "wardrobe.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    root = logging.getLogger()
    for old in root.handlers[:]:  # idempotent across repeated setup calls
        root.removeHandler(old)
        old.close()
    root.setLevel(settings.log_level.upper())
    for handler in (file_handler, logging.StreamHandler()):
        handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(handler)
