"""Seed a small test wardrobe. Run: ``python -m app.repository.seed`` (uses the configured DB).

All values come from the taxonomy (``app/config/taxonomy.json``); writes are validated, so a
typo here fails loudly instead of creating bad data.
"""

import uuid
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.taxonomy import get_taxonomy
from app.repository.db import make_engine, migrate
from app.repository.models import Garment

# Each entry: display name, category, subcategory, color, pattern, formality (1 casual .. 5
# formal), style tags, layering role, category-specific details.
_GARMENTS: list[dict[str, Any]] = [
    {"n": "White T-shirt", "c": "top", "s": "t_shirt", "col": "white", "f": 1,
     "st": ["casual", "classic"], "l": "base",
     "d": {"collar": "crew_neck", "sleeve_length": "short", "closure": "pullover", "fit": "regular"}},
    {"n": "Black T-shirt", "c": "top", "s": "t_shirt", "col": "black", "f": 1,
     "st": ["casual", "understated"], "l": "base",
     "d": {"collar": "crew_neck", "sleeve_length": "short", "closure": "pullover", "fit": "slim"}},
    {"n": "Blue Oxford shirt", "c": "top", "s": "shirt", "col": "blue", "f": 3,
     "st": ["smart_casual", "classic"], "l": "base",
     "d": {"collar": "button_down", "sleeve_length": "long", "closure": "buttons", "fit": "regular"}},
    {"n": "White dress shirt", "c": "top", "s": "shirt", "col": "white", "f": 4,
     "st": ["formal", "classic"], "l": "base",
     "d": {"collar": "spread", "sleeve_length": "long", "closure": "buttons", "fit": "slim"}},
    {"n": "Navy overshirt", "c": "layer", "s": "overshirt", "col": "navy", "f": 2,
     "st": ["casual", "understated"], "l": "mid",
     "d": {"collar": "standard", "closure": "buttons", "fit": "relaxed"}},
    {"n": "Charcoal blazer", "c": "layer", "s": "blazer", "col": "charcoal", "f": 4,
     "st": ["formal", "classic"], "l": "outer",
     "d": {"collar": "notch_lapel", "sleeve_length": "long", "closure": "buttons", "fit": "slim"}},
    {"n": "Black jeans", "c": "bottom", "s": "jeans", "col": "black", "f": 2,
     "st": ["casual"], "l": None,
     "d": {"fit": "slim", "rise": "mid", "length": "full", "closure": "zip_button"}},
    {"n": "Blue jeans", "c": "bottom", "s": "jeans", "col": "blue", "f": 1,
     "st": ["casual"], "l": None,
     "d": {"fit": "straight", "rise": "mid", "length": "full", "closure": "zip_button"}},
    {"n": "Beige chinos", "c": "bottom", "s": "chinos", "col": "beige", "f": 3,
     "st": ["smart_casual"], "l": None,
     "d": {"fit": "tapered", "rise": "mid", "length": "ankle", "closure": "zip_button"}},
    {"n": "Black trousers", "c": "bottom", "s": "trousers", "col": "black", "f": 4,
     "st": ["formal", "classic"], "l": None,
     "d": {"fit": "slim", "rise": "mid", "length": "full", "closure": "hook_eye"}},
    {"n": "White sneakers", "c": "footwear", "s": "sneakers", "col": "white", "f": 1,
     "st": ["casual"], "l": None, "d": {"closure": "laces", "heel": "flat", "toe": "round"}},
    {"n": "Brown loafers", "c": "footwear", "s": "loafers", "col": "brown", "f": 3,
     "st": ["smart_casual"], "l": None, "d": {"closure": "slip_on", "heel": "low", "toe": "almond"}},
    {"n": "Black oxford shoes", "c": "footwear", "s": "oxfords", "col": "black", "f": 5,
     "st": ["formal"], "l": None, "d": {"closure": "laces", "heel": "low", "toe": "round"}},
    {"n": "Cream kurta", "c": "ethnic", "s": "kurta", "col": "cream", "f": 3,
     "st": ["traditional"], "l": None,
     "d": {"neckline": "mandarin", "sleeve_length": "long", "length": "knee", "silhouette": "straight"}},
]  # fmt: skip


def seed_wardrobe(engine: Engine) -> list[str]:
    """Insert the sample garments in one transaction; returns their ids.

    Raises ``TaxonomyError`` if a sample value is not in the taxonomy (nothing is inserted).
    """
    taxonomy = get_taxonomy()
    with Session(engine) as session, session.begin():
        garments = []
        for item in _GARMENTS:
            fields = {
                "category": item["c"],
                "subcategory": item["s"],
                "primary_color": item["col"],
                "pattern": "solid",
                "formality": item["f"],
                "style_tags": item["st"],
                "layering_role": item["l"],
                "details": item["d"],
            }
            taxonomy.validate_fields(fields)
            garments.append(Garment(id=str(uuid.uuid4()), display_name=item["n"], **fields))
        session.add_all(garments)
        return [g.id for g in garments]


if __name__ == "__main__":
    settings = get_settings()
    assert settings.db_path is not None
    engine = make_engine(settings.db_path)
    migrate(engine)
    print(f"Seeded {len(seed_wardrobe(engine))} garments into {settings.db_path}")
