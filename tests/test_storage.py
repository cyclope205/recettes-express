"""Tests for StockManager and SuggestionsStore (storage.py).

No pytest-homeassistant-custom-component fixture is used here: CI only
installs plain homeassistant + pytest, so hass and the Store's async I/O
are replaced with lightweight unittest.mock stand-ins, and async methods
are driven through a plain asyncio.run() wrapper rather than pytest-asyncio.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.recettes_express.storage import StockManager, SuggestionsStore


def run(coro):
    return asyncio.run(coro)


def _make_manager() -> StockManager:
    hass = MagicMock()
    manager = StockManager(hass)
    # Store does real file I/O in async_save - never call that against a
    # bare MagicMock hass. Stub _async_save so tests never touch disk.
    manager._async_save = AsyncMock()
    return manager


def _make_suggestions_store() -> SuggestionsStore:
    hass = MagicMock()
    return SuggestionsStore(hass)


# --- async_add_item / get_items -----------------------------------------


def test_async_add_item_returns_id_and_stores_item():
    manager = _make_manager()
    item_id = run(manager.async_add_item("Tomate", 3, "piece", "2026-01-01"))
    items = manager.get_items()
    assert len(items) == 1
    assert items[0]["id"] == item_id
    assert items[0]["name"] == "Tomate"
    assert items[0]["quantity"] == 3
    assert items[0]["unit"] == "piece"
    assert items[0]["expiration_date"] == "2026-01-01"


def test_async_add_item_calls_save():
    manager = _make_manager()
    run(manager.async_add_item("Tomate", 3, "piece", "2026-01-01"))
    manager._async_save.assert_awaited()


def test_get_items_sorted_by_expiration_date_ascending():
    manager = _make_manager()
    run(manager.async_add_item("Lait", 1, "l", "2026-03-01"))
    run(manager.async_add_item("Oeufs", 6, "piece", "2026-01-15"))
    run(manager.async_add_item("Farine", 1, "kg", "2026-02-01"))
    items = manager.get_items()
    assert [i["name"] for i in items] == ["Oeufs", "Farine", "Lait"]


# --- get_items_by_ids -----------------------------------------------------


def test_get_items_by_ids_returns_only_requested():
    manager = _make_manager()
    id1 = run(manager.async_add_item("Tomate", 3, "piece", "2026-01-01"))
    run(manager.async_add_item("Lait", 1, "l", "2026-03-01"))
    result = manager.get_items_by_ids([id1])
    assert len(result) == 1
    assert result[0]["id"] == id1


def test_get_items_by_ids_ignores_unknown_ids():
    manager = _make_manager()
    run(manager.async_add_item("Tomate", 3, "piece", "2026-01-01"))
    result = manager.get_items_by_ids(["unknown-id"])
    assert result == []


# --- get_expiring_soon -----------------------------------------------------


def test_get_expiring_soon_includes_items_within_window():
    manager = _make_manager()
    from datetime import date, timedelta

    soon = (date.today() + timedelta(days=1)).isoformat()
    far = (date.today() + timedelta(days=30)).isoformat()
    run(manager.async_add_item("Yaourt", 1, "piece", soon))
    run(manager.async_add_item("Conserve", 1, "boite", far))
    result = manager.get_expiring_soon(days=3)
    assert len(result) == 1
    assert result[0]["name"] == "Yaourt"


def test_get_expiring_soon_ignores_items_without_expiration_date():
    manager = _make_manager()
    manager._items["x"] = {
        "id": "x", "name": "Sans DLC", "quantity": 1, "unit": "piece",
        "expiration_date": None, "added_at": None,
    }
    result = manager.get_expiring_soon(days=3)
    assert result == []


# --- async_update_item -----------------------------------------------------


def test_async_update_item_updates_fields():
    manager = _make_manager()
    item_id = run(manager.async_add_item("Tomate", 3, "piece", "2026-01-01"))
    ok = run(manager.async_update_item(item_id, quantity=5))
    assert ok is True
    items = manager.get_items_by_ids([item_id])
    assert items[0]["quantity"] == 5
    assert items[0]["name"] == "Tomate"


def test_async_update_item_unknown_id_returns_false():
    manager = _make_manager()
    ok = run(manager.async_update_item("nope", quantity=5))
    assert ok is False


# --- async_remove_item -----------------------------------------------------


def test_async_remove_item_removes_and_returns_true():
    manager = _make_manager()
    item_id = run(manager.async_add_item("Tomate", 3, "piece", "2026-01-01"))
    ok = run(manager.async_remove_item(item_id))
    assert ok is True
    assert manager.get_items() == []


def test_async_remove_item_unknown_id_returns_false():
    manager = _make_manager()
    ok = run(manager.async_remove_item("nope"))
    assert ok is False


# --- async_load validation --------------------------------------------------


def test_async_load_valid_data_populates_items():
    manager = _make_manager()
    manager._store.async_load = AsyncMock(return_value={
        "items": {
            "abc": {
                "id": "abc", "name": "Tomate", "quantity": 2,
                "unit": "piece", "expiration_date": "2026-01-01",
                "added_at": "2026-01-01T00:00:00",
            }
        }
    })
    run(manager.async_load())
    items = manager.get_items()
    assert len(items) == 1
    assert items[0]["name"] == "Tomate"


def test_async_load_none_data_results_in_empty_stock():
    manager = _make_manager()
    manager._store.async_load = AsyncMock(return_value=None)
    run(manager.async_load())
    assert manager.get_items() == []


def test_async_load_wrong_shape_results_in_empty_stock():
    manager = _make_manager()
    manager._store.async_load = AsyncMock(return_value={"items": "not-a-dict"})
    run(manager.async_load())
    assert manager.get_items() == []


def test_async_load_drops_entries_missing_name():
    manager = _make_manager()
    manager._store.async_load = AsyncMock(return_value={
        "items": {
            "ok": {"id": "ok", "name": "Tomate", "quantity": 1, "unit": "piece"},
            "bad": {"id": "bad", "quantity": 1, "unit": "piece"},
        }
    })
    run(manager.async_load())
    items = manager.get_items()
    assert len(items) == 1
    assert items[0]["name"] == "Tomate"


def test_async_load_drops_entries_missing_unit():
    manager = _make_manager()
    manager._store.async_load = AsyncMock(return_value={
        "items": {"bad": {"id": "bad", "name": "Tomate", "quantity": 1}}
    })
    run(manager.async_load())
    assert manager.get_items() == []


def test_async_load_drops_non_dict_entries():
    manager = _make_manager()
    manager._store.async_load = AsyncMock(return_value={
        "items": {"bad": "not-a-dict"}
    })
    run(manager.async_load())
    assert manager.get_items() == []


def test_async_load_invalid_quantity_defaults_to_one():
    manager = _make_manager()
    manager._store.async_load = AsyncMock(return_value={
        "items": {
            "abc": {
                "id": "abc", "name": "Tomate", "quantity": "beaucoup",
                "unit": "piece",
            }
        }
    })
    run(manager.async_load())
    items = manager.get_items()
    assert items[0]["quantity"] == 1


def test_async_load_invalid_expiration_date_becomes_none():
    manager = _make_manager()
    manager._store.async_load = AsyncMock(return_value={
        "items": {
            "abc": {
                "id": "abc", "name": "Tomate", "quantity": 1,
                "unit": "piece", "expiration_date": 12345,
            }
        }
    })
    run(manager.async_load())
    items = manager.get_items()
    assert items[0]["expiration_date"] is None


# --- SuggestionsStore -------------------------------------------------------


def test_suggestions_store_get_defaults_to_empty_list():
    store = _make_suggestions_store()
    assert store.get() == []


def test_suggestions_store_async_load_populates_recipes():
    store = _make_suggestions_store()
    store._store.async_load = AsyncMock(return_value={"recipes": [{"title": "Soupe"}]})
    run(store.async_load())
    assert store.get() == [{"title": "Soupe"}]


def test_suggestions_store_async_load_none_data_results_in_empty_list():
    store = _make_suggestions_store()
    store._store.async_load = AsyncMock(return_value=None)
    run(store.async_load())
    assert store.get() == []


def test_suggestions_store_async_load_wrong_shape_results_in_empty_list():
    store = _make_suggestions_store()
    store._store.async_load = AsyncMock(return_value={"recipes": "not-a-list"})
    run(store.async_load())
    assert store.get() == []


def test_suggestions_store_async_set_persists_and_updates_get():
    store = _make_suggestions_store()
    store._store.async_save = AsyncMock()
    run(store.async_set([{"title": "Soupe"}]))
    assert store.get() == [{"title": "Soupe"}]
    store._store.async_save.assert_awaited_with({"recipes": [{"title": "Soupe"}]})
