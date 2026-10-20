"""Seed a small test wardrobe. Run: ``python -m app.repository.seed`` (uses the configured DB)."""

import uuid

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.repository.db import make_engine, migrate
from app.repository.models import Garment

# name, category, subcategory, color, pattern, formality (1 casual .. 5 formal), styles, layering
# Category strings are placeholders until the taxonomy lands (BE-E1-S6).
_GARMENTS: list[tuple[str, str, str, str, str, int, list[str], str | None]] = [
    ("White T-shirt", "top", "t-shirt", "white", "solid", 1, ["casual", "classic"], "base"),
    ("Black T-shirt", "top", "t-shirt", "black", "solid", 1, ["casual", "understated"], "base"),
    ("Blue Oxford shirt", "top", "shirt", "blue", "solid", 3, ["smart casual", "classic"], "base"),
    ("White dress shirt", "top", "shirt", "white", "solid", 4, ["formal", "classic"], "base"),
    ("Navy overshirt", "layer", "overshirt", "navy", "solid", 2, ["casual", "understated"], "mid"),
    ("Charcoal blazer", "layer", "blazer", "charcoal", "solid", 4, ["formal", "classic"], "outer"),
    ("Black jeans", "bottom", "jeans", "black", "solid", 2, ["casual"], None),
    ("Blue jeans", "bottom", "jeans", "blue", "solid", 1, ["casual"], None),
    ("Beige chinos", "bottom", "chinos", "beige", "solid", 3, ["smart casual"], None),
    ("Black trousers", "bottom", "trousers", "black", "solid", 4, ["formal", "classic"], None),
    ("White sneakers", "footwear", "sneakers", "white", "solid", 1, ["casual"], None),
    ("Brown loafers", "footwear", "loafers", "brown", "solid", 3, ["smart casual"], None),
    ("Black oxford shoes", "footwear", "oxfords", "black", "solid", 5, ["formal"], None),
    ("Cream kurta", "ethnic", "kurta", "cream", "solid", 3, ["traditional"], None),
]


def seed_wardrobe(engine: Engine) -> list[str]:
    """Insert the sample garments in one transaction; returns their ids."""
    with Session(engine) as session, session.begin():
        garments = [
            Garment(
                id=str(uuid.uuid4()),
                display_name=name,
                category=cat,
                subcategory=sub,
                primary_color=color,
                pattern=pattern,
                formality=formality,
                style_tags=styles,
                layering_role=layer,
            )
            for name, cat, sub, color, pattern, formality, styles, layer in _GARMENTS
        ]
        session.add_all(garments)
        return [g.id for g in garments]


if __name__ == "__main__":
    settings = get_settings()
    assert settings.db_path is not None
    engine = make_engine(settings.db_path)
    migrate(engine)
    print(f"Seeded {len(seed_wardrobe(engine))} garments into {settings.db_path}")
