import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Select, exists, func, literal, or_, select
from sqlalchemy.orm import Session

from app.repository.models import Garment, GarmentImage, Processing
from app.repository.util import utcnow_iso

EDITABLE_FIELDS = frozenset(
    {
        "display_name",
        "category",
        "subcategory",
        "primary_color",
        "secondary_colors",
        "pattern",
        "formality",
        "style_tags",
        "season_tags",
        "layering_role",
        "availability_status",
    }
)


@dataclass(frozen=True)
class GarmentFilter:
    category: str | None = None
    color: str | None = None  # matches primary or secondary colors
    style: str | None = None  # one style tag
    tag: str | None = None  # one season tag
    pattern: str | None = None
    availability: str | None = None
    processing_status: str | None = None
    q: str | None = None  # free-text over name, category, subcategory, color


def _json_has(column: Any, value: str) -> ColumnElement[bool]:
    each = func.json_each(column).table_valued("value")
    return select(literal(1)).select_from(each).where(each.c.value == value).exists()


def _check_fields(fields: dict[str, Any]) -> None:
    unknown = fields.keys() - EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"Unknown garment fields: {sorted(unknown)}")


class GarmentRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, display_name: str, **fields: Any) -> Garment:
        _check_fields(fields)
        garment = Garment(id=str(uuid.uuid4()), display_name=display_name, **fields)
        self._s.add(garment)
        self._s.flush()
        return garment

    def get(self, garment_id: str, *, include_deleted: bool = False) -> Garment | None:
        garment = self._s.get(Garment, garment_id)
        if garment is None or (garment.deleted_at is not None and not include_deleted):
            return None
        return garment

    def _filtered(self, f: GarmentFilter) -> Select[Any]:
        stmt = select(Garment).where(Garment.deleted_at.is_(None))
        if f.category:
            stmt = stmt.where(Garment.category == f.category)
        if f.color:
            stmt = stmt.where(
                or_(Garment.primary_color == f.color, _json_has(Garment.secondary_colors, f.color))
            )
        if f.style:
            stmt = stmt.where(_json_has(Garment.style_tags, f.style))
        if f.tag:
            stmt = stmt.where(_json_has(Garment.season_tags, f.tag))
        if f.pattern:
            stmt = stmt.where(Garment.pattern == f.pattern)
        if f.availability:
            stmt = stmt.where(Garment.availability_status == f.availability)
        if f.processing_status:
            stmt = stmt.where(
                exists().where(
                    Processing.garment_id == Garment.id, Processing.status == f.processing_status
                )
            )
        if f.q:
            stmt = stmt.where(
                or_(
                    Garment.display_name.contains(f.q, autoescape=True),
                    Garment.category.contains(f.q, autoescape=True),
                    Garment.subcategory.contains(f.q, autoescape=True),
                    Garment.primary_color.contains(f.q, autoescape=True),
                )
            )
        return stmt

    def list(
        self, f: GarmentFilter | None = None, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[Garment], int]:
        """Return one page (newest first) and the total number of matches."""
        stmt = self._filtered(f or GarmentFilter())
        total = self._s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        page = stmt.order_by(Garment.created_at.desc(), Garment.id).limit(limit).offset(offset)
        return list(self._s.scalars(page)), total

    def update(self, garment_id: str, **fields: Any) -> Garment | None:
        """Set the given fields (``None`` clears one). Returns ``None`` if the garment is gone."""
        _check_fields(fields)
        garment = self.get(garment_id)
        if garment is None:
            return None
        for name, value in fields.items():
            setattr(garment, name, value)
        garment.updated_at = utcnow_iso()
        self._s.flush()
        return garment

    def soft_delete(self, garment_id: str) -> bool:
        garment = self.get(garment_id)
        if garment is None:
            return False
        garment.deleted_at = utcnow_iso()
        self._s.flush()
        return True

    def add_image(
        self,
        garment_id: str,
        original_path: str,
        content_type: str,
        file_size: int,
        thumbnail_path: str | None = None,
    ) -> GarmentImage:
        """Record a stored photo for a garment.

        Paths are *relative* storage paths as returned by ``StorageService.save``.
        """
        image = GarmentImage(
            id=str(uuid.uuid4()),
            garment_id=garment_id,
            original_path=original_path,
            thumbnail_path=thumbnail_path,
            content_type=content_type,
            file_size=file_size,
        )
        self._s.add(image)
        self._s.flush()
        return image

    def get_image(self, garment_id: str) -> GarmentImage | None:
        """Return the newest image record of a garment, or ``None`` if it has none."""
        stmt = (
            select(GarmentImage)
            .where(GarmentImage.garment_id == garment_id)
            .order_by(GarmentImage.created_at.desc(), GarmentImage.id)
            .limit(1)
        )
        return self._s.scalars(stmt).first()
