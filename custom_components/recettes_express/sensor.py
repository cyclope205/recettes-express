"""Entites sensor pour Recettes Express."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_STOCK_UPDATED
from .storage import StockManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Cree les entites sensor pour cette entree."""
    stock: StockManager = hass.data[DOMAIN][entry.entry_id]["stock"]

    async_add_entities(
        [
            StockCountSensor(entry, stock),
            ExpiringSoonSensor(entry, stock),
        ]
    )


class _PushUpdatedSensor(SensorEntity):
    """Base : pas de polling, se met a jour immediatement via le dispatcher."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_STOCK_UPDATED, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class StockCountSensor(_PushUpdatedSensor):
    """Nombre total d'aliments en stock, avec le detail en attribut."""

    _attr_icon = "mdi:food-variant"

    def __init__(self, entry: ConfigEntry, stock: StockManager) -> None:
        self._stock = stock
        self._attr_name = "Aliments"
        self._attr_unique_id = f"{entry.entry_id}_count"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Recettes Express",
            manufacturer="Recettes Express",
            model="Suivi de stock",
        )

    @property
    def native_value(self) -> int:
        return len(self._stock.get_items())

    @property
    def extra_state_attributes(self) -> dict:
        return {"items": self._stock.get_items()}


class ExpiringSoonSensor(_PushUpdatedSensor):
    """Nombre d'aliments bientot perimes, avec le detail en attribut."""

    _attr_icon = "mdi:clock-alert-outline"

    def __init__(self, entry: ConfigEntry, stock: StockManager) -> None:
        self._stock = stock
        self._attr_name = "Bientot perime"
        self._attr_unique_id = f"{entry.entry_id}_expiring_soon"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Recettes Express",
            manufacturer="Recettes Express",
            model="Suivi de stock",
        )

    @property
    def native_value(self) -> int:
        return len(self._stock.get_expiring_soon())

    @property
    def extra_state_attributes(self) -> dict:
        return {"items": self._stock.get_expiring_soon()}
