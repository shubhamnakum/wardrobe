"""Garment endpoints. Currently: serving a garment's photo and thumbnail."""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import StorageDep, UowDep
from app.storage import InvalidStoragePath

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/garments", tags=["garments"])

# Stops browsers from guessing a different content type than the one we store.
_HEADERS = {"X-Content-Type-Options": "nosniff"}


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
