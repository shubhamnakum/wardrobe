"""Taxonomy endpoint: the lists the UI needs to fill its dropdowns."""

from fastapi import APIRouter

from app.domain.taxonomy import Taxonomy, get_taxonomy

router = APIRouter(prefix="/api", tags=["taxonomy"])


@router.get("/taxonomy", response_model=Taxonomy)
def read_taxonomy() -> Taxonomy:
    """Return the garment taxonomy: categories (with subcategories and detail options), colors,
    patterns, formality scale, layering roles, seasons and style tags.

    ``version`` increases whenever the lists change, so clients can cache by version.
    """
    return get_taxonomy()
