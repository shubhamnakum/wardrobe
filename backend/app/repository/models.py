"""SQLAlchemy models. Source of truth for the schema; Alembic autogenerates migrations from here.

Timestamps are UTC ISO-8601 text. JSON columns are also guarded by a ``json_valid`` CHECK.
``garment`` holds the *effective* attribute values; ``attribute_evidence`` keeps provenance.
"""

from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_NOW = text("(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))")


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def _json() -> Any:
    return JSON(none_as_null=True)  # Python None -> SQL NULL, not JSON 'null'


class Garment(Base):
    __tablename__ = "garment"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)
    subcategory: Mapped[str | None] = mapped_column(String)
    primary_color: Mapped[str | None] = mapped_column(String)
    secondary_colors: Mapped[list[str] | None] = mapped_column(_json())
    pattern: Mapped[str | None] = mapped_column(String)
    formality: Mapped[int | None] = mapped_column(Integer)
    style_tags: Mapped[list[str] | None] = mapped_column(_json())
    season_tags: Mapped[list[str] | None] = mapped_column(_json())
    layering_role: Mapped[str | None] = mapped_column(String)
    # Category-specific details such as {"collar": "mandarin", "fit": "slim"}; see taxonomy.
    details: Mapped[dict[str, str] | None] = mapped_column(_json())
    availability_status: Mapped[str] = mapped_column(String, server_default="available")
    deleted_at: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, server_default=_NOW)
    updated_at: Mapped[str] = mapped_column(String, server_default=_NOW)

    __table_args__ = (
        CheckConstraint(
            "availability_status IN ('available', 'unavailable')", name="availability_status"
        ),
        CheckConstraint(
            "secondary_colors IS NULL OR json_valid(secondary_colors)", name="secondary_colors_json"
        ),
        CheckConstraint("style_tags IS NULL OR json_valid(style_tags)", name="style_tags_json"),
        CheckConstraint("season_tags IS NULL OR json_valid(season_tags)", name="season_tags_json"),
        CheckConstraint("details IS NULL OR json_valid(details)", name="details_json"),
        # ponytail: style_tags is JSON and not plain-indexable; tag filters scan (fine ~500 items).
        Index("idx_garment_category", "category"),
        Index("idx_garment_primary_color", "primary_color"),
        Index("idx_garment_availability", "availability_status", "deleted_at"),
    )


class GarmentImage(Base):
    __tablename__ = "garment_image"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    garment_id: Mapped[str] = mapped_column(ForeignKey("garment.id", ondelete="CASCADE"))
    original_path: Mapped[str] = mapped_column(String)
    thumbnail_path: Mapped[str | None] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    file_size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String, server_default=_NOW)

    __table_args__ = (
        CheckConstraint("file_size >= 0", name="file_size"),
        Index("idx_garment_image_garment", "garment_id"),
    )


class Processing(Base):
    __tablename__ = "processing"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    garment_id: Mapped[str] = mapped_column(ForeignKey("garment.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String, server_default="uploaded")
    error_summary: Mapped[str | None] = mapped_column(String)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[str] = mapped_column(String, server_default=_NOW)
    updated_at: Mapped[str] = mapped_column(String, server_default=_NOW)

    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded', 'processing', 'ready', 'needs_review', 'failed')",
            name="status",
        ),
        Index("idx_processing_garment", "garment_id"),
        Index("idx_processing_status", "status"),
    )


class AttributeEvidence(Base):
    __tablename__ = "attribute_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    garment_id: Mapped[str] = mapped_column(ForeignKey("garment.id", ondelete="CASCADE"))
    attribute_name: Mapped[str] = mapped_column(String)
    value: Mapped[Any | None] = mapped_column(_json())  # NULL = unknown / cleared
    source: Mapped[str] = mapped_column(String)
    confidence: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String)
    confirmed_at: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, server_default=_NOW)

    __table_args__ = (
        CheckConstraint("source IN ('model', 'user')", name="source"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence"
        ),
        Index("idx_evidence_garment_attr", "garment_id", "attribute_name"),
        {"sqlite_autoincrement": True},
    )


class Outfit(Base):
    __tablename__ = "outfit"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    brief_snapshot: Mapped[dict[str, Any] | None] = mapped_column(_json())
    style_label: Mapped[str | None] = mapped_column(String)
    explanation: Mapped[str | None] = mapped_column(Text)
    score_out_of_10: Mapped[float | None] = mapped_column(Float)
    score_factors: Mapped[dict[str, Any] | None] = mapped_column(_json())
    is_saved: Mapped[bool] = mapped_column(Boolean, server_default="0")
    is_favorite: Mapped[bool] = mapped_column(Boolean, server_default="0")
    created_at: Mapped[str] = mapped_column(String, server_default=_NOW)

    __table_args__ = (
        CheckConstraint(
            "score_out_of_10 IS NULL OR (score_out_of_10 >= 0 AND score_out_of_10 <= 10)",
            name="score_out_of_10",
        ),
        CheckConstraint(
            "brief_snapshot IS NULL OR json_valid(brief_snapshot)", name="brief_snapshot_json"
        ),
        CheckConstraint(
            "score_factors IS NULL OR json_valid(score_factors)", name="score_factors_json"
        ),
        Index("idx_outfit_saved", "is_saved"),
        Index("idx_outfit_favorite", "is_favorite"),
    )


class OutfitItem(Base):
    __tablename__ = "outfit_item"

    outfit_id: Mapped[str] = mapped_column(
        ForeignKey("outfit.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    garment_id: Mapped[str] = mapped_column(ForeignKey("garment.id"))  # no cascade: see DEC-010
    role: Mapped[str] = mapped_column(String)

    __table_args__ = (Index("idx_outfit_item_garment", "garment_id"),)


class Preference(Base):
    __tablename__ = "preference"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)
    weight: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[str] = mapped_column(String, server_default=_NOW)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    outfit_id: Mapped[str] = mapped_column(ForeignKey("outfit.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, server_default=_NOW)

    __table_args__ = (
        CheckConstraint("action IN ('like', 'dislike', 'skip', 'worn')", name="action"),
        Index("idx_feedback_outfit", "outfit_id"),
        {"sqlite_autoincrement": True},
    )


class UsageEvent(Base):
    __tablename__ = "usage_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    garment_id: Mapped[str] = mapped_column(ForeignKey("garment.id"))
    event_type: Mapped[str] = mapped_column(String)
    outfit_id: Mapped[str | None] = mapped_column(ForeignKey("outfit.id", ondelete="SET NULL"))
    timestamp: Mapped[str] = mapped_column(String, server_default=_NOW)

    __table_args__ = (
        Index("idx_usage_garment", "garment_id", "timestamp"),
        {"sqlite_autoincrement": True},
    )
