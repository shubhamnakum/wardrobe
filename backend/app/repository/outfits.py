import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repository.models import Feedback, Outfit, OutfitItem

_OUTFIT_FIELDS = frozenset(
    {"brief_snapshot", "style_label", "explanation", "score_out_of_10", "score_factors"}
)


class OutfitRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, items: Sequence[tuple[str, str]], **fields: Any) -> Outfit:
        """Create an outfit from ``(garment_id, role)`` pairs; position follows list order."""
        unknown = fields.keys() - _OUTFIT_FIELDS
        if unknown:
            raise ValueError(f"Unknown outfit fields: {sorted(unknown)}")
        outfit = Outfit(id=str(uuid.uuid4()), **fields)
        self._s.add(outfit)
        self._s.flush()  # no relationship() defined: insert parent before children
        for position, (garment_id, role) in enumerate(items):
            self._s.add(
                OutfitItem(outfit_id=outfit.id, position=position, garment_id=garment_id, role=role)
            )
        self._s.flush()
        return outfit

    def get(self, outfit_id: str) -> Outfit | None:
        return self._s.get(Outfit, outfit_id)

    def items(self, outfit_id: str) -> list[OutfitItem]:
        stmt = select(OutfitItem).where(OutfitItem.outfit_id == outfit_id)
        return list(self._s.scalars(stmt.order_by(OutfitItem.position)))

    def list(
        self,
        *,
        saved: bool | None = None,
        favorite: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Outfit]:
        stmt = select(Outfit)
        if saved is not None:
            stmt = stmt.where(Outfit.is_saved == saved)
        if favorite is not None:
            stmt = stmt.where(Outfit.is_favorite == favorite)
        stmt = stmt.order_by(Outfit.created_at.desc(), Outfit.id).limit(limit).offset(offset)
        return list(self._s.scalars(stmt))

    def set_saved(self, outfit_id: str, value: bool) -> bool:
        outfit = self.get(outfit_id)
        if outfit is None:
            return False
        outfit.is_saved = value
        self._s.flush()
        return True

    def set_favorite(self, outfit_id: str, value: bool) -> bool:
        outfit = self.get(outfit_id)
        if outfit is None:
            return False
        outfit.is_favorite = value
        self._s.flush()
        return True


class FeedbackRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, outfit_id: str, action: str, reason: str | None = None) -> Feedback:
        row = Feedback(outfit_id=outfit_id, action=action, reason=reason)
        self._s.add(row)
        self._s.flush()
        return row

    def list_for_outfit(self, outfit_id: str) -> list[Feedback]:
        stmt = select(Feedback).where(Feedback.outfit_id == outfit_id).order_by(Feedback.id)
        return list(self._s.scalars(stmt))
