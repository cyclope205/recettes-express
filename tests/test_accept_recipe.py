"""End-to-end test for the accept_recipe service handler.

Chains the full path suggest_recipes-derived used_items -> accept_recipe ->
StockManager.async_consume_items -> final stock, which each unit test in
test_storage.py / test_gemini_client.py only exercises in isolation. No
pytest-homeassistant-custom-component fixture is used, consistent with the
rest of this repo's tests: hass is a lightweight MagicMock and the
service handlers registered by _async_register_services are captured
directly instead of being invoked through hass.services.async_call.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.recettes_express import _async_register_services
from custom_components.recettes_express.const import (
    ATTR_RECIPE_INDEX,
    DATA_LAST_SUGGESTIONS,
    DOMAIN,
    SERVICE_ACCEPT_RECIPE,
)
from custom_components.recettes_express.storage import StockManager
from homeassistant.exceptions import HomeAssistantError


def run(coro):
    return asyncio.run(coro)


def _make_manager() -> StockManager:
    hass = MagicMock()
    manager = StockManager(hass)
    manager._async_save = AsyncMock()
    return manager


def _register_and_capture(manager, suggestions):
    hass = MagicMock()
    suggestions_store = MagicMock()
    suggestions_store.get.return_value = suggestions
    hass.data = {
        DOMAIN: {"entry1": {"stock": manager, DATA_LAST_SUGGESTIONS: suggestions_store}}
    }
    hass.services.has_service.return_value = False
    registered = {}

    def _register(domain, service, handler, **kwargs):
        registered[service] = handler

    hass.services.async_register.side_effect = _register
    _async_register_services(hass, MagicMock())
    return registered


def test_accept_recipe_end_to_end_consumes_only_used_quantity():
    manager = _make_manager()
    eggs_id = run(manager.async_add_item("Oeufs", 6, "piece", "2026-01-01"))

    recipe = {
        "title": "Omelette",
        "used_items": [{"item_id": eggs_id, "quantity": 2, "unit": "piece"}],
    }
    registered = _register_and_capture(manager, [recipe])

    call = MagicMock()
    call.data = {ATTR_RECIPE_INDEX: 0}
    result = run(registered[SERVICE_ACCEPT_RECIPE](call))

    assert result == {"accepted": "Omelette", "removed_count": 1}
    items = manager.get_items_by_ids([eggs_id])
    assert items[0]["quantity"] == 4


def test_accept_recipe_removes_item_fully_consumed():
    manager = _make_manager()
    eggs_id = run(manager.async_add_item("Oeufs", 2, "piece", "2026-01-01"))

    recipe = {
        "title": "Omelette geante",
        "used_items": [{"item_id": eggs_id, "quantity": 2, "unit": "piece"}],
    }
    registered = _register_and_capture(manager, [recipe])

    call = MagicMock()
    call.data = {ATTR_RECIPE_INDEX: 0}
    run(registered[SERVICE_ACCEPT_RECIPE](call))

    assert manager.get_items_by_ids([eggs_id]) == []


def test_accept_recipe_raises_and_changes_nothing_when_stock_insufficient():
    manager = _make_manager()
    eggs_id = run(manager.async_add_item("Oeufs", 1, "piece", "2026-01-01"))

    recipe = {
        "title": "Omelette",
        "used_items": [{"item_id": eggs_id, "quantity": 2, "unit": "piece"}],
    }
    registered = _register_and_capture(manager, [recipe])

    call = MagicMock()
    call.data = {ATTR_RECIPE_INDEX: 0}
    try:
        run(registered[SERVICE_ACCEPT_RECIPE](call))
        assert False, "should have raised HomeAssistantError"
    except HomeAssistantError:
        pass

    items = manager.get_items_by_ids([eggs_id])
    assert items[0]["quantity"] == 1


def test_accept_recipe_raises_when_recipe_index_out_of_bounds():
    manager = _make_manager()
    run(manager.async_add_item("Oeufs", 6, "piece", "2026-01-01"))

    recipe = {
        "title": "Omelette",
        "used_items": [{"item_id": "whatever", "quantity": 2, "unit": "piece"}],
    }
    registered = _register_and_capture(manager, [recipe])

    call = MagicMock()
    call.data = {ATTR_RECIPE_INDEX: 5}
    try:
        run(registered[SERVICE_ACCEPT_RECIPE](call))
        assert False, "should have raised HomeAssistantError"
    except HomeAssistantError:
        pass

def test_accept_recipe_raises_when_recipe_index_negative():
    manager = _make_manager()
    run(manager.async_add_item("Oeufs", 6, "piece", "2026-01-01"))

    recipe = {
        "title": "Omelette",
        "used_items": [{"item_id": "whatever", "quantity": 2, "unit": "piece"}],
    }
    registered = _register_and_capture(manager, [recipe])

    call = MagicMock()
    call.data = {ATTR_RECIPE_INDEX: -1}
    try:
        run(registered[SERVICE_ACCEPT_RECIPE](call))
        assert False, "should have raised HomeAssistantError"
    except HomeAssistantError:
        pass
