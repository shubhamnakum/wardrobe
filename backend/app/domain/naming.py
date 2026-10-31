"""Garment display name generation (BE-E1-S7-T1).

Provides deterministic name generation utility functions for garments using their
attributes (color, pattern, fit, subcategory, category).
"""

from collections.abc import Mapping
from typing import Any

# Special-case formatting for common clothing terms
_SPECIAL_TOKENS: dict[str, str] = {
    "t_shirt": "T-Shirt",
    "co_ord_set": "Co-ord Set",
    "v_neck": "V-Neck",
    "button_down": "Button-Down",
}

# Fits considered neutral/default that can be omitted for concise names
_DEFAULT_FITS: frozenset[str] = frozenset(["regular"])

# Hard cap on generated name length to prevent runaway display strings
MAX_DISPLAY_NAME_LENGTH: int = 100


def format_token(token: str) -> str:
    """Format a lower_snake_case token into title case, respecting compound terms.

    Args:
        token: A lower_snake_case string such as 'navy', 't_shirt', or 'coral_peach'.

    Returns:
        A human-readable Title Case string such as 'Navy', 'T-Shirt', or 'Coral Peach'.
    """
    if not token:
        return ""
    token = token.strip()
    if token in _SPECIAL_TOKENS:
        return _SPECIAL_TOKENS[token]
    return token.replace("_", " ").title()


def generate_display_name(
    *,
    category: str | None = None,
    subcategory: str | None = None,
    primary_color: str | None = None,
    pattern: str | None = None,
    details: Mapping[str, Any] | None = None,
    max_length: int = MAX_DISPLAY_NAME_LENGTH,
) -> str:
    """Generate a readable display name from garment attributes.

    Order: [Color] [Pattern] [Fit] [Subcategory or Category]
    Rules:
        - Omit pattern 'solid' when a color is present (e.g. 'Navy Shirt', not 'Navy Solid Shirt').
        - Omit fit 'regular' when color or subcategory is present to avoid redundant noise.
        - Fall back to subcategory if present, else category, else 'Garment'.
        - Cap the resulting string to ``max_length`` characters.

    Args:
        category: Garment broad category (e.g. 'top', 'bottom', 'ethnic').
        subcategory: Garment specific type (e.g. 'shirt', 'jeans', 'kurta').
        primary_color: Primary color name (e.g. 'navy', 'white', 'coral_peach').
        pattern: Pattern name (e.g. 'striped', 'solid', 'floral').
        details: Category-specific details map (may contain 'fit', 'collar', etc.).
        max_length: Maximum allowed length for the returned display name.

    Returns:
        A clean human-readable name, at most ``max_length`` characters long.
    """
    parts: list[str] = []

    # 1. Color
    if primary_color:
        parts.append(format_token(primary_color))

    # 2. Distinctive Pattern (omit 'solid' if color is already present)
    if pattern:
        if pattern != "solid" or not primary_color:
            parts.append(format_token(pattern))

    # 3. Distinctive Fit (from details if present)
    if details and isinstance(details, Mapping):
        fit = details.get("fit")
        if isinstance(fit, str) and fit not in _DEFAULT_FITS:
            parts.append(format_token(fit))

    # 4. Base noun: subcategory or category, falling back to 'Garment'
    if subcategory:
        parts.append(format_token(subcategory))
    elif category:
        parts.append(format_token(category))
    else:
        parts.append("Garment")

    name = " ".join(parts).strip()
    if len(name) > max_length:
        return name[:max_length].rstrip()
    return name

