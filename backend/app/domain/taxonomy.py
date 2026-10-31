"""The garment taxonomy: the official lists of categories, colors, patterns and so on.

The lists live in a versioned JSON file (``app/config/taxonomy.json``) so they can be changed
without touching code. This module loads and validates that file, and provides the checks the
rest of the app uses:

* :meth:`Taxonomy.validate_fields` - reject writes that use values outside the lists.
* :meth:`Taxonomy.sanitize` - clean AI output: values outside the lists become ``None``.
* :meth:`Taxonomy.merge_details` - apply an edit to a garment's category-specific details.

Some fields are **open**: ``colors``, ``patterns``, and ``style_tags`` are curated suggestions
but users may supply custom values not in the list (e.g. a color like ``coral_peach`` or a
tag like ``dopamine_dressing``). AI output for open fields is still sanitized to ``None`` if
unknown — only human writes are trusted with custom values.

Each category also defines *detail* attributes (collar, closure, fit, ...) with their allowed
values, because which details make sense depends on the type of garment.
"""

import json
import re
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.config import get_settings

DEFAULT_TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "config" / "taxonomy.json"

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Fields that users may extend with custom lower_snake_case values beyond the curated list.
# AI output for these fields is still sanitized (unknown → None). Only human writes are trusted.
_OPEN_FIELD_NAMES: frozenset[str] = frozenset(
    ["primary_color", "secondary_colors", "pattern", "style_tags"]
)


class TaxonomyError(ValueError):
    """Raised when a write uses values that are not in the taxonomy.

    ``errors`` holds one short human-readable message per problem.
    """

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def _check_names(what: str, values: Iterable[str]) -> None:
    """Make sure ``values`` are non-empty, lower_snake_case and unique (used when loading)."""
    seen: set[str] = set()
    for value in values:
        if not _NAME.match(value):
            raise ValueError(f"{what}: '{value}' must be lower_snake_case")
        if value in seen:
            raise ValueError(f"{what}: '{value}' is listed twice")
        seen.add(value)
    if not seen:
        raise ValueError(f"{what}: must not be empty")


def _is_valid_custom_value(value: str) -> bool:
    """Return True if ``value`` is a valid lower_snake_case custom value.

    Used to validate user-supplied values for open fields (colors, patterns, style_tags).
    Custom values follow the same naming rules as taxonomy entries so they are safe to store
    and display consistently.
    """
    return bool(_NAME.match(value))


class FormalityScale(BaseModel):
    """The formality scale, for example 1 (very casual) to 5 (formal), with a label per step."""

    min: int
    max: int
    labels: dict[int, str]

    @model_validator(mode="after")
    def _check(self) -> "FormalityScale":
        """The labels must cover every step from ``min`` to ``max`` exactly."""
        if self.min >= self.max:
            raise ValueError("formality: min must be below max")
        if set(self.labels) != set(range(self.min, self.max + 1)):
            raise ValueError("formality: labels must cover every step of the scale")
        return self


class ColorDef(BaseModel):
    """One color of the palette: a name and a hex value for drawing swatches in the UI."""

    name: str
    hex: str

    @model_validator(mode="after")
    def _check(self) -> "ColorDef":
        """The hex value must look like ``#RRGGBB``."""
        if not _HEX.match(self.hex):
            raise ValueError(f"color '{self.name}': hex must look like #RRGGBB")
        return self


class CategoryDef(BaseModel):
    """A garment category with its subcategories and its category-specific detail attributes."""

    name: str
    subcategories: list[str]
    details: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> "CategoryDef":
        """Names must be clean and unique; every detail attribute needs at least one value."""
        _check_names(f"category '{self.name}' subcategories", self.subcategories)
        for key, values in self.details.items():
            _check_names(f"category '{self.name}' detail '{key}'", [key])
            _check_names(f"category '{self.name}' detail '{key}' values", values)
        return self


class Taxonomy(BaseModel):
    """The whole taxonomy as loaded from the JSON file.

    ``version`` is a whole number that is increased whenever the file changes, so clients can
    tell when to refresh cached copies.

    ``open_fields`` lists the fields (e.g. ``primary_color``, ``pattern``, ``style_tags``) that
    accept user-supplied custom values beyond the curated lists. AI output is still sanitized for
    all fields; only human writes can use custom values.
    """

    version: int = Field(ge=1)
    formality: FormalityScale
    layering_roles: list[str]
    seasons: list[str]
    style_tags: list[str]
    patterns: list[str]
    colors: list[ColorDef]
    categories: list[CategoryDef]
    open_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "Taxonomy":
        """Every list must have clean, unique names (so the file cannot be silently broken)."""
        _check_names("layering_roles", self.layering_roles)
        _check_names("seasons", self.seasons)
        _check_names("style_tags", self.style_tags)
        _check_names("patterns", self.patterns)
        _check_names("colors", [c.name for c in self.colors])
        _check_names("categories", [c.name for c in self.categories])
        return self

    # ---- lookups ------------------------------------------------------------------------

    def category(self, name: str | None) -> CategoryDef | None:
        """Return the category called ``name``, or ``None`` if there is no such category."""
        return next((c for c in self.categories if c.name == name), None)

    def _color_names(self) -> set[str]:
        """The set of palette color names."""
        return {c.name for c in self.colors}

    def _single_value_sets(self) -> dict[str, set[str]]:
        """Allowed values for the fields that hold exactly one value."""
        return {
            "category": {c.name for c in self.categories},
            "primary_color": self._color_names(),
            "pattern": set(self.patterns),
            "layering_role": set(self.layering_roles),
        }

    def _list_value_sets(self) -> dict[str, set[str]]:
        """Allowed values for the fields that hold a list of values."""
        return {
            "secondary_colors": self._color_names(),
            "style_tags": set(self.style_tags),
            "season_tags": set(self.seasons),
        }

    def _formality_ok(self, value: Any) -> bool:
        """True if ``value`` is a whole number on the formality scale."""
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and self.formality.min <= value <= self.formality.max
        )

    def is_open(self, field: str) -> bool:
        """Return True if ``field`` accepts user-supplied custom values beyond the curated list.

        Open fields (colors, patterns, style_tags) still validate that custom values use
        lower_snake_case. AI output is never trusted for custom values.
        """
        return field in _OPEN_FIELD_NAMES

    # ---- checks for writes --------------------------------------------------------------

    def validate_fields(
        self, fields: Mapping[str, Any], current: Mapping[str, Any] | None = None
    ) -> None:
        """Check the fields of a write against the taxonomy; raise :class:`TaxonomyError`.

        ``fields`` are the values being written (``None`` always means "clear" and is allowed).
        ``current`` are the garment's existing values, used when a write changes only one half
        of a pair, for example a new ``category`` while ``subcategory`` stays as it was. The
        check covers every error found, not just the first.

        **Open fields** (primary_color, secondary_colors, pattern, style_tags): values in the
        curated list are always accepted. Values *not* in the list are also accepted from the
        user as long as they are lower_snake_case — the taxonomy list acts as *suggestions*, not
        a hard constraint for human writes.
        """
        cur = current or {}
        errors: list[str] = []

        def resulting(name: str) -> Any:
            """The value a field will have after the write."""
            return fields[name] if name in fields else cur.get(name)

        for name, allowed in self._single_value_sets().items():
            value = fields.get(name)
            if value is None:
                continue
            if value in allowed:
                continue  # always OK — it's in the curated list
            if self.is_open(name):
                # Custom user value: must still be lower_snake_case
                if not _is_valid_custom_value(value):
                    errors.append(
                        f"{name}: '{value}' must be lower_snake_case"
                        f" (e.g. 'coral_peach', not 'Coral Peach')"
                    )
            else:
                errors.append(f"{name}: '{value}' is not allowed")

        for name, allowed in self._list_value_sets().items():
            for value in fields.get(name) or []:
                if value in allowed:
                    continue  # in curated list
                if self.is_open(name):
                    if not _is_valid_custom_value(value):
                        errors.append(
                            f"{name}: '{value}' must be lower_snake_case"
                            f" (e.g. 'earthy_rust', not 'Earthy Rust')"
                        )
                else:
                    errors.append(f"{name}: '{value}' is not allowed")

        if fields.get("formality") is not None and not self._formality_ok(fields["formality"]):
            errors.append(
                f"formality: must be a whole number {self.formality.min}-{self.formality.max}"
            )

        category = self.category(resulting("category"))
        if "category" in fields or "subcategory" in fields:
            sub = resulting("subcategory")
            if sub is not None:
                if category is None:
                    errors.append("subcategory: set a valid category first")
                elif sub not in category.subcategories:
                    errors.append(f"subcategory: '{sub}' does not belong to '{category.name}'")
        if "category" in fields or "details" in fields:
            details = resulting("details") or {}
            if details and category is None:
                errors.append("details: set a valid category first")
            elif category is not None:
                for key, value in details.items():
                    allowed_values = category.details.get(key)
                    if allowed_values is None:
                        errors.append(f"details.{key}: not defined for category '{category.name}'")
                    elif value not in allowed_values:
                        errors.append(f"details.{key}: '{value}' is not allowed")
        if errors:
            raise TaxonomyError(errors)

    # ---- details helpers ----------------------------------------------------------------

    def prune_details(
        self, category: str | None, details: Mapping[str, str] | None
    ) -> dict[str, str]:
        """Keep only the details that are valid for ``category`` (used when a category changes)."""
        cat = self.category(category)
        if cat is None or not details:
            return {}
        return {k: v for k, v in details.items() if v in cat.details.get(k, [])}

    def merge_details(
        self,
        category: str | None,
        current: Mapping[str, str] | None,
        patch: Mapping[str, str | None],
    ) -> dict[str, str] | None:
        """Apply an edit to a garment's details and return the new details.

        Details that do not fit ``category`` are dropped first, then every key in ``patch`` is
        set - or removed when its value is ``None``. Returns ``None`` when nothing is left.
        The result is *not* validated here; :meth:`validate_fields` does that on write.
        """
        merged: dict[str, str] = self.prune_details(category, current)
        for key, value in patch.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        return merged or None

    # ---- cleaning AI output -------------------------------------------------------------

    def sanitize(self, attrs: Mapping[str, Any]) -> dict[str, Any]:
        """Clean model-predicted attributes: anything outside the taxonomy becomes ``None``.

        Only keys present in ``attrs`` are returned. In list fields invalid items are dropped
        (``None`` if none are left). ``subcategory`` and ``details`` are kept only if they fit
        the (valid) category. AI output is untrusted, so this never raises.

        Note: open fields (colors, patterns, style_tags) are still sanitized strictly for AI
        output — the AI cannot invent custom values; only the user can.
        """
        out: dict[str, Any] = dict(attrs)
        singles = self._single_value_sets()
        for name, allowed in singles.items():
            if name in out and out[name] not in allowed:
                out[name] = None
        for name, allowed in self._list_value_sets().items():
            if name in out:
                value = out[name]
                kept = [v for v in value if v in allowed] if isinstance(value, list) else []
                out[name] = kept or None
        if "formality" in out and not self._formality_ok(out["formality"]):
            out["formality"] = None

        category = self.category(out.get("category") if "category" in out else None)
        if "subcategory" in out and (
            category is None or out["subcategory"] not in category.subcategories
        ):
            out["subcategory"] = None
        if "details" in out:
            raw = out["details"] if isinstance(out["details"], Mapping) else {}
            cleaned = self.prune_details(category.name if category else None, raw)
            out["details"] = cleaned or None
        return out


def load_taxonomy(path: Path) -> Taxonomy:
    """Read and validate a taxonomy JSON file; raise ``ValueError`` naming the file if invalid."""
    try:
        return Taxonomy.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Invalid taxonomy file {path}: {exc}") from exc


@lru_cache
def get_taxonomy() -> Taxonomy:
    """Return the app-wide taxonomy (loaded once; path from settings, else the packaged file)."""
    return load_taxonomy(get_settings().taxonomy_path or DEFAULT_TAXONOMY_PATH)
