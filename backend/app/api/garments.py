"""Garment endpoints: browse, detail, edit, soft-delete, and serving photos/thumbnails."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse

from app.api.deps import StorageDep, UowDep
from app.api.schemas import (
    AttributeProvenance,
    GarmentDetail,
    GarmentPage,
    GarmentSummary,
    GarmentUpdate,
    ImageInfo,
    ProcessingInfo,
)
from app.domain.taxonomy import get_taxonomy
from app.repository.garments import ATTRIBUTE_FIELDS, GarmentFilter
from app.repository.models import AttributeEvidence, Garment, GarmentImage, Processing
from app.repository.unit_of_work import UnitOfWork
from app.repository.util import utcnow_iso
from app.storage import InvalidStoragePath

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/garments", tags=["garments"])

# Stops browsers from guessing a different content type than the one we store.
_HEADERS = {"X-Content-Type-Options": "nosniff"}

# Evidence for category-specific details is stored as "details.<key>", for example "details.collar".
_DETAILS_PREFIX = "details."


def _not_found() -> HTTPException:
    """The single 404 used when a garment does not exist (or was deleted)."""
    return HTTPException(status_code=404, detail="Garment not found")


def _summary_fields(
    garment: Garment, image: GarmentImage | None, processing: Processing | None
) -> dict[str, Any]:
    """Build the fields shared by the list item and the detail view."""
    return {
        "id": garment.id,
        "display_name": garment.display_name,
        "category": garment.category,
        "subcategory": garment.subcategory,
        "primary_color": garment.primary_color,
        "secondary_colors": garment.secondary_colors,
        "pattern": garment.pattern,
        "formality": garment.formality,
        "style_tags": garment.style_tags,
        "season_tags": garment.season_tags,
        "layering_role": garment.layering_role,
        "details": garment.details,
        "availability_status": garment.availability_status,
        "processing_status": processing.status if processing else None,
        "thumbnail_url": (
            f"/api/garments/{garment.id}/thumbnail" if image and image.thumbnail_path else None
        ),
        "created_at": garment.created_at,
        "updated_at": garment.updated_at,
    }


def _provenance(
    garment: Garment, evidence: list[AttributeEvidence]
) -> dict[str, AttributeProvenance]:
    """Work out, per AI attribute, the current value and the evidence behind it.

    The current value is always the one stored on the garment. The evidence shown is the newest
    user entry if there is one (user beats model), otherwise the newest model prediction.
    """
    result: dict[str, AttributeProvenance] = {}
    for name in ATTRIBUTE_FIELDS:
        rows = [e for e in evidence if e.attribute_name == name]
        user = [e for e in rows if e.source == "user"]
        chosen = user[-1] if user else (rows[-1] if rows else None)
        result[name] = AttributeProvenance(
            value=getattr(garment, name),
            source=chosen.source if chosen else None,
            confidence=chosen.confidence if chosen else None,
            model_version=chosen.model_version if chosen else None,
            confirmed_at=chosen.confirmed_at if chosen else None,
            confirmed=bool(chosen and chosen.source == "user" and chosen.confirmed_at),
        )
    # Category-specific details have evidence named "details.<key>".
    keys = set(garment.details or {}) | {
        e.attribute_name.removeprefix(_DETAILS_PREFIX)
        for e in evidence
        if e.attribute_name.startswith(_DETAILS_PREFIX)
    }
    for key in sorted(keys):
        name = _DETAILS_PREFIX + key
        rows = [e for e in evidence if e.attribute_name == name]
        user = [e for e in rows if e.source == "user"]
        chosen = user[-1] if user else (rows[-1] if rows else None)
        result[name] = AttributeProvenance(
            value=(garment.details or {}).get(key),
            source=chosen.source if chosen else None,
            confidence=chosen.confidence if chosen else None,
            model_version=chosen.model_version if chosen else None,
            confirmed_at=chosen.confirmed_at if chosen else None,
            confirmed=bool(chosen and chosen.source == "user" and chosen.confirmed_at),
        )
    return result


def _detail(uow: UnitOfWork, garment: Garment) -> GarmentDetail:
    """Assemble the full detail view of a garment (images, processing, provenance)."""
    images = uow.garments.list_images(garment.id)
    processing = uow.garments.processing_for([garment.id]).get(garment.id)
    newest_image = images[-1] if images else None
    return GarmentDetail(
        **_summary_fields(garment, newest_image, processing),
        images=[
            ImageInfo(
                id=i.id,
                content_type=i.content_type,
                file_size=i.file_size,
                image_url=f"/api/garments/{garment.id}/image",
                thumbnail_url=(
                    f"/api/garments/{garment.id}/thumbnail" if i.thumbnail_path else None
                ),
                created_at=i.created_at,
            )
            for i in images
        ],
        processing=(
            ProcessingInfo(
                status=processing.status,
                error_summary=processing.error_summary,
                attempts=processing.attempts,
            )
            if processing
            else None
        ),
        attributes=_provenance(garment, uow.evidence.list_for_garment(garment.id)),
    )


@router.get("", response_model=GarmentPage)
def list_garments(
    uow: UowDep,
    category: Annotated[str | None, Query(max_length=100)] = None,
    color: Annotated[str | None, Query(max_length=100)] = None,
    style: Annotated[str | None, Query(max_length=100)] = None,
    tag: Annotated[str | None, Query(max_length=100)] = None,
    pattern: Annotated[str | None, Query(max_length=100)] = None,
    availability: Annotated[str | None, Query(max_length=20)] = None,
    status: Annotated[str | None, Query(max_length=20)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GarmentPage:
    """List garments, newest first, with optional filters and paging.

    Filters combine with AND. ``color`` matches primary or secondary colors, ``style`` and
    ``tag`` match one style / season tag exactly, ``status`` is the AI processing status
    (ready, needs_review, ...), ``availability`` is available/unavailable and ``q`` searches
    name, category, subcategory and color. Deleted garments are never listed.
    """
    flt = GarmentFilter(
        category=category,
        color=color,
        style=style,
        tag=tag,
        pattern=pattern,
        availability=availability,
        processing_status=status,
        q=q,
    )
    garments, total = uow.garments.list(flt, limit=limit, offset=offset)
    ids = [g.id for g in garments]
    images = uow.garments.images_for(ids)
    processing = uow.garments.processing_for(ids)
    items = [
        GarmentSummary(**_summary_fields(g, images.get(g.id), processing.get(g.id)))
        for g in garments
    ]
    return GarmentPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{garment_id}", response_model=GarmentDetail)
def get_garment(garment_id: str, uow: UowDep) -> GarmentDetail:
    """Return one garment with its images, processing state and attribute provenance."""
    garment = uow.garments.get(garment_id)
    if garment is None:
        raise _not_found()
    return _detail(uow, garment)


@router.patch("/{garment_id}", response_model=GarmentDetail)
def update_garment(garment_id: str, body: GarmentUpdate, uow: UowDep) -> GarmentDetail:
    """Edit a garment. Only the fields in the body change; ``null`` clears an AI attribute.

    Every AI attribute in the body is recorded as user-confirmed evidence, even when the value
    is unchanged (this is how "looks right" confirmations are stored). ``details`` is merged
    into the existing details (a key set to ``null`` is removed) and each key gets its own
    ``details.<key>`` evidence. Values must be in the taxonomy (422 otherwise). User-confirmed
    values are never overwritten by later model runs.
    """
    fields = body.model_dump(mode="json", exclude_unset=True)
    garment = uow.garments.get(garment_id)
    if garment is None:
        raise _not_found()
    details_patch: dict[str, str | None] | None = fields.pop("details", None)
    if details_patch is not None or "category" in fields:
        # Changing the category drops details that no longer fit; then the patch is applied.
        category = fields["category"] if "category" in fields else garment.category
        merged = get_taxonomy().merge_details(category, garment.details, details_patch or {})
        if merged != garment.details:
            fields["details"] = merged
    updated = uow.garments.update(garment_id, **fields)
    if updated is None:
        raise _not_found()
    garment = updated
    confirmed_at = utcnow_iso()
    for name in ATTRIBUTE_FIELDS:
        if name in fields:
            uow.evidence.add(garment_id, name, fields[name], "user", confirmed_at=confirmed_at)
    for key, value in (details_patch or {}).items():
        uow.evidence.add(
            garment_id, _DETAILS_PREFIX + key, value, "user", confirmed_at=confirmed_at
        )
    return _detail(uow, garment)


@router.delete("/{garment_id}", status_code=204)
def delete_garment(garment_id: str, uow: UowDep) -> Response:
    """Soft-delete a garment: it disappears from lists and recommendations.

    The row, its evidence and its image files are kept; permanent removal is a separate step
    (BE-E5-S7). Returns 404 if the garment does not exist or is already deleted.
    """
    if not uow.garments.soft_delete(garment_id):
        raise _not_found()
    return Response(status_code=204)


def _serve_image(
    garment_id: str, uow: UowDep, storage: StorageDep, *, thumbnail: bool
) -> FileResponse:
    """Look up the garment's image record and return its file.

    The file is found only through the database record, never from a path in the request, so
    only files that belong to an existing (not deleted) garment can be served. Every failure
    returns the same short 404 so callers cannot probe the filesystem.
    """
    not_found = HTTPException(status_code=404, detail="Image not found")
    if uow.garments.get(garment_id) is None:
        raise not_found
    image = uow.garments.get_image(garment_id)
    stored = None if image is None else (image.thumbnail_path if thumbnail else image.original_path)
    if image is None or not stored:
        raise not_found
    try:
        path = storage.resolve(stored)
    except InvalidStoragePath:
        log.error("Garment %s has an invalid stored image path", garment_id)
        raise not_found from None
    if not path.is_file():
        log.error("Garment %s image file is missing on disk", garment_id)
        raise not_found
    return FileResponse(path, media_type=image.content_type, headers=_HEADERS)


@router.get("/{garment_id}/image")
def get_garment_image(garment_id: str, uow: UowDep, storage: StorageDep) -> FileResponse:
    """Return the original photo of a garment (404 if it has none)."""
    return _serve_image(garment_id, uow, storage, thumbnail=False)


@router.get("/{garment_id}/thumbnail")
def get_garment_thumbnail(garment_id: str, uow: UowDep, storage: StorageDep) -> FileResponse:
    """Return the thumbnail of a garment (404 if it has none)."""
    return _serve_image(garment_id, uow, storage, thumbnail=True)
