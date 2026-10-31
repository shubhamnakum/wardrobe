"""Request and response models (Pydantic) for the garment API.

These describe exactly what goes over the wire. Pydantic checks incoming data against them,
so bad input is rejected with a 422 before any of our code runs.
"""

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Availability(StrEnum):
    """Whether a garment can be used in recommendations."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


# Allowed value shapes for editable text fields.
_Text = Annotated[str, Field(min_length=1, max_length=100)]
_TagList = Annotated[list[Annotated[str, Field(min_length=1, max_length=50)]], Field(max_length=20)]
_Key = Annotated[str, Field(min_length=1, max_length=50)]


class GarmentUpdate(BaseModel):
    """Body of ``PATCH /api/garments/{id}``: only the fields you send are changed.

    Sending a field as ``null`` clears it (allowed for AI attributes, not for ``display_name`` or
    ``availability_status``). Unknown fields and an empty body are rejected.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    category: _Text | None = None
    subcategory: _Text | None = None
    primary_color: _Text | None = None
    secondary_colors: _TagList | None = None
    pattern: _Text | None = None
    formality: Annotated[int, Field(ge=1, le=5)] | None = None  # 1 casual .. 5 formal
    style_tags: _TagList | None = None
    season_tags: _TagList | None = None
    layering_role: _Text | None = None
    # Category-specific details (collar, closure, fit, ...). Merged into the existing details:
    # a key set to a value is set, a key set to null is removed. The object itself cannot be null.
    details: dict[_Key, _Key | None] | None = Field(default=None, max_length=20)
    availability_status: Availability | None = None

    @model_validator(mode="after")
    def _check_body(self) -> "GarmentUpdate":
        """Reject an empty body and explicit ``null`` for fields that cannot be cleared."""
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        for name in ("display_name", "availability_status", "details"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be cleared")
        return self


class GarmentSummary(BaseModel):
    """One garment as shown in the wardrobe grid."""

    id: str
    display_name: str
    category: str | None
    subcategory: str | None
    primary_color: str | None
    secondary_colors: list[str] | None
    pattern: str | None
    formality: int | None
    style_tags: list[str] | None
    season_tags: list[str] | None
    layering_role: str | None
    details: dict[str, str] | None
    availability_status: str
    processing_status: str | None  # latest processing state, if the garment was uploaded
    thumbnail_url: str | None
    created_at: str
    updated_at: str


class GarmentPage(BaseModel):
    """A page of garments plus the total number of matches (for paging controls)."""

    items: list[GarmentSummary]
    total: int
    limit: int
    offset: int


class ImageInfo(BaseModel):
    """A stored photo of a garment."""

    id: str
    content_type: str
    file_size: int
    image_url: str
    thumbnail_url: str | None
    created_at: str


class ProcessingInfo(BaseModel):
    """Where AI processing of a garment stands."""

    status: str
    error_summary: str | None
    attempts: int


class AttributeProvenance(BaseModel):
    """The current value of one attribute and where it came from.

    ``source`` is ``"user"`` for values the user entered or confirmed, ``"model"`` for AI
    predictions and ``None`` when nothing has been recorded yet.
    """

    value: Any
    source: Literal["model", "user"] | None
    confidence: float | None
    model_version: str | None
    confirmed_at: str | None
    confirmed: bool


class GarmentDetail(GarmentSummary):
    """A garment with its images, processing state and per-attribute provenance."""

    images: list[ImageInfo]
    processing: ProcessingInfo | None
    attributes: dict[str, AttributeProvenance]
