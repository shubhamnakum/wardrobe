"""Tests for garment display name generation (BE-E1-S7-T1)."""

from app.domain.naming import (
    MAX_DISPLAY_NAME_LENGTH,
    format_token,
    generate_display_name,
)


def test_format_token_handles_standard_snake_case() -> None:
    """Standard snake_case strings are converted to title case words."""
    assert format_token("navy") == "Navy"
    assert format_token("coral_peach") == "Coral Peach"
    assert format_token("smart_casual") == "Smart Casual"


def test_format_token_handles_special_fashion_terms() -> None:
    """Common clothing terms with hyphens or specific capitalization retain formatting."""
    assert format_token("t_shirt") == "T-Shirt"
    assert format_token("co_ord_set") == "Co-ord Set"
    assert format_token("v_neck") == "V-Neck"
    assert format_token("button_down") == "Button-Down"


def test_format_token_handles_empty_or_whitespace() -> None:
    """Empty or whitespace strings return empty string."""
    assert format_token("") == ""
    assert format_token("   ") == ""


def test_generate_display_name_basic_combinations() -> None:
    """Color, fit and subcategory form a natural English name."""
    assert (
        generate_display_name(
            primary_color="navy",
            subcategory="shirt",
            details={"fit": "slim"},
        )
        == "Navy Slim Shirt"
    )
    assert (
        generate_display_name(
            primary_color="black",
            subcategory="jeans",
            details={"fit": "skinny"},
        )
        == "Black Skinny Jeans"
    )
    assert (
        generate_display_name(
            primary_color="white",
            subcategory="t_shirt",
        )
        == "White T-Shirt"
    )


def test_generate_display_name_omits_solid_when_color_present() -> None:
    """Pattern 'solid' is omitted when color is already specified."""
    assert (
        generate_display_name(
            primary_color="navy",
            pattern="solid",
            subcategory="shirt",
        )
        == "Navy Shirt"
    )
    assert (
        generate_display_name(
            pattern="solid",
            subcategory="shirt",
        )
        == "Solid Shirt"
    )


def test_generate_display_name_includes_distinctive_patterns() -> None:
    """Distinctive patterns such as striped, checked or floral are included with color."""
    assert (
        generate_display_name(
            primary_color="navy",
            pattern="striped",
            subcategory="shirt",
        )
        == "Navy Striped Shirt"
    )
    assert (
        generate_display_name(
            primary_color="maroon",
            pattern="embroidered",
            subcategory="kurta",
        )
        == "Maroon Embroidered Kurta"
    )


def test_generate_display_name_omits_regular_fit() -> None:
    """Neutral fit 'regular' is omitted to avoid noisy titles."""
    assert (
        generate_display_name(
            primary_color="grey",
            subcategory="trousers",
            details={"fit": "regular"},
        )
        == "Grey Trousers"
    )


def test_generate_display_name_fallback_to_category() -> None:
    """When subcategory is missing, category is used as the base noun."""
    assert (
        generate_display_name(
            primary_color="blue",
            category="top",
        )
        == "Blue Top"
    )
    assert (
        generate_display_name(
            primary_color="khaki",
            category="bottom",
            details={"fit": "relaxed"},
        )
        == "Khaki Relaxed Bottom"
    )


def test_generate_display_name_fallback_to_garment() -> None:
    """When neither category nor subcategory is present, falls back to Garment."""
    assert generate_display_name() == "Garment"
    assert generate_display_name(primary_color="navy") == "Navy Garment"
    assert (
        generate_display_name(
            primary_color="coral_peach",
            pattern="floral",
        )
        == "Coral Peach Floral Garment"
    )


def test_generate_display_name_enforces_max_length() -> None:
    """Output string is truncated to max_length if it exceeds the limit."""
    long_name = generate_display_name(
        primary_color="extra_super_long_custom_color_description_name",
        pattern="intricate_traditional_hand_woven_pattern",
        subcategory="ceremonial_traditional_festive_sherwani",
        max_length=40,
    )
    assert len(long_name) <= 40
    assert MAX_DISPLAY_NAME_LENGTH == 100
