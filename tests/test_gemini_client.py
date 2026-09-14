"""Tests for the Gemini JSON-response validation helpers (gemini_client.py).

Gemini is an LLM: nothing guarantees its response matches the schema asked
for in the prompt. These tests exercise the defensive parsing/normalization
layer that never trusts the raw JSON and drops or coerces anything that
doesn't fit, instead of raising or propagating bad data.
"""
from __future__ import annotations

import pytest

from custom_components.recettes_express.gemini_client import (
    GeminiError,
    _coerce_number,
    _coerce_str,
    _extract_json,
    _normalize_detected_items,
    _normalize_recipes,
)


# --- _extract_json -----------------------------------------------------


def test_extract_json_parses_plain_json():
    result = _extract_json('{"items": []}')
    assert result == {"items": []}


def test_extract_json_strips_markdown_code_fence():
    result = _extract_json('```json\n{"items": []}\n```')
    assert result == {"items": []}


def test_extract_json_strips_bare_code_fence_without_json_label():
    result = _extract_json('```\n{"items": []}\n```')
    assert result == {"items": []}


def test_extract_json_raises_on_invalid_json():
    with pytest.raises(GeminiError):
        _extract_json("not json at all")


def test_extract_json_raises_when_top_level_is_not_an_object():
    with pytest.raises(GeminiError):
        _extract_json("[1, 2, 3]")


# --- _coerce_str -----------------------------------------------------


def test_coerce_str_strips_whitespace():
    assert _coerce_str("  hello  ") == "hello"


def test_coerce_str_none_returns_default():
    assert _coerce_str(None, "fallback") == "fallback"


def test_coerce_str_non_string_is_stringified():
    assert _coerce_str(42) == "42"


# --- _coerce_number -----------------------------------------------------


def test_coerce_number_passes_through_int_and_float():
    assert _coerce_number(5) == 5
    assert _coerce_number(2.5) == 2.5


def test_coerce_number_rejects_bool_explicitly():
    # bool is a subclass of int in Python - must not silently become 1/0.
    assert _coerce_number(True, default=9.0) == 9.0
    assert _coerce_number(False, default=9.0) == 9.0


def test_coerce_number_parses_numeric_string():
    assert _coerce_number("3.5") == 3.5


def test_coerce_number_invalid_string_returns_default():
    assert _coerce_number("beaucoup", default=1.0) == 1.0


def test_coerce_number_none_returns_default():
    assert _coerce_number(None, default=7.0) == 7.0


# --- _normalize_detected_items -----------------------------------------------------


def test_normalize_detected_items_valid_entry():
    items = _normalize_detected_items([
        {"name": "Tomate", "quantity": 3, "unit": "piece", "expiration_date": "2026-01-01"}
    ])
    assert items == [
        {"name": "Tomate", "quantity": 3, "unit": "piece", "expiration_date": "2026-01-01"}
    ]


def test_normalize_detected_items_non_list_returns_empty():
    assert _normalize_detected_items({"not": "a list"}) == []
    assert _normalize_detected_items(None) == []


def test_normalize_detected_items_skips_non_dict_entries():
    items = _normalize_detected_items(["not a dict", 42])
    assert items == []


def test_normalize_detected_items_drops_entries_without_name():
    items = _normalize_detected_items([{"quantity": 1, "unit": "piece"}])
    assert items == []


def test_normalize_detected_items_invalid_unit_falls_back_to_piece():
    items = _normalize_detected_items([{"name": "Tomate", "unit": "litres-cubiques"}])
    assert items[0]["unit"] == "piece"


def test_normalize_detected_items_missing_quantity_defaults_to_one():
    items = _normalize_detected_items([{"name": "Tomate", "unit": "piece"}])
    assert items[0]["quantity"] == 1.0


def test_normalize_detected_items_blank_expiration_date_becomes_none():
    items = _normalize_detected_items([{"name": "Tomate", "unit": "piece", "expiration_date": "  "}])
    assert items[0]["expiration_date"] is None


def test_normalize_detected_items_non_string_expiration_date_becomes_none():
    items = _normalize_detected_items([{"name": "Tomate", "unit": "piece", "expiration_date": 20260101}])
    assert items[0]["expiration_date"] is None


def test_normalize_detected_items_null_expiration_date_stays_none():
    items = _normalize_detected_items([{"name": "Tomate", "unit": "piece", "expiration_date": None}])
    assert items[0]["expiration_date"] is None


# --- _normalize_recipes -----------------------------------------------------


def test_normalize_recipes_valid_entry():
    recipes = _normalize_recipes(
        [{"title": "Soupe", "used_item_ids": ["a", "b"], "prep_minutes": 20, "steps": ["Couper", "Cuire"]}],
        valid_item_ids={"a", "b"},
    )
    assert len(recipes) == 1
    assert recipes[0]["title"] == "Soupe"
    assert recipes[0]["used_item_ids"] == ["a", "b"]
    assert recipes[0]["prep_minutes"] == 20
    assert recipes[0]["steps"] == ["Couper", "Cuire"]


def test_normalize_recipes_non_list_returns_empty():
    assert _normalize_recipes({"not": "a list"}) == []
    assert _normalize_recipes(None) == []


def test_normalize_recipes_drops_entries_without_title():
    recipes = _normalize_recipes([{"steps": ["Couper"]}])
    assert recipes == []


def test_normalize_recipes_drops_entries_with_no_valid_steps():
    recipes = _normalize_recipes([{"title": "Soupe", "steps": []}])
    assert recipes == []
    recipes = _normalize_recipes([{"title": "Soupe", "steps": "not a list"}])
    assert recipes == []


def test_normalize_recipes_filters_used_item_ids_against_valid_set():
    # Second, code-level barrier against invented ingredients: an id that
    # doesn't actually exist in the caller's stock must be dropped even
    # if Gemini included it in the response.
    recipes = _normalize_recipes(
        [{"title": "Soupe", "used_item_ids": ["a", "invented"], "steps": ["Cuire"]}],
        valid_item_ids={"a"},
    )
    assert recipes[0]["used_item_ids"] == ["a"]


def test_normalize_recipes_without_valid_item_ids_filter_keeps_all():
    recipes = _normalize_recipes(
        [{"title": "Soupe", "used_item_ids": ["a", "b"], "steps": ["Cuire"]}],
        valid_item_ids=None,
    )
    assert recipes[0]["used_item_ids"] == ["a", "b"]


def test_normalize_recipes_used_item_ids_non_list_becomes_empty():
    recipes = _normalize_recipes([{"title": "Soupe", "used_item_ids": "a", "steps": ["Cuire"]}])
    assert recipes[0]["used_item_ids"] == []


def test_normalize_recipes_used_item_ids_bool_entries_excluded():
    recipes = _normalize_recipes([{"title": "Soupe", "used_item_ids": [True, "a"], "steps": ["Cuire"]}])
    assert recipes[0]["used_item_ids"] == ["a"]


def test_normalize_recipes_prep_minutes_defaults_to_zero():
    recipes = _normalize_recipes([{"title": "Soupe", "steps": ["Cuire"]}])
    assert recipes[0]["prep_minutes"] == 0


def test_normalize_recipes_steps_drops_blank_entries():
    recipes = _normalize_recipes([{"title": "Soupe", "steps": ["Cuire", "  ", ""]}])
    assert recipes[0]["steps"] == ["Cuire"]


def test_normalize_recipes_skips_non_dict_entries():
    recipes = _normalize_recipes(["not a dict", 42])
    assert recipes == []
