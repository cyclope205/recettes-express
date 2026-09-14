"""Gestion du stock d'aliments pour Recettes Express."""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_EXPIRING_SOON_DAYS,
    SIGNAL_STOCK_UPDATED,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


class StockManager:
    """Charge, modifie et persiste la liste des aliments en stock."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._items: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        """Charge le stock depuis le disque."""
        data = await self._store.async_load()
        self._items = data.get("items", {}) if data else {}

    async def _async_save(self) -> None:
        await self._store.async_save({"items": self._items})
        async_dispatcher_send(self._hass, SIGNAL_STOCK_UPDATED)

    def get_items(self) -> list[dict[str, Any]]:
        """Retourne tous les aliments, tries par DLC la plus proche."""
        items = list(self._items.values())
        return sorted(items, key=lambda i: i.get("expiration_date") or "9999-99-99")

    def get_items_by_ids(self, item_ids: list[str]) -> list[dict[str, Any]]:
        """Retourne les aliments correspondant aux id fournis (ceux trouves)."""
        wanted = set(item_ids)
        return [item for item in self.get_items() if item["id"] in wanted]

    def get_expiring_soon(
        self, days: int = DEFAULT_EXPIRING_SOON_DAYS
    ) -> list[dict[str, Any]]:
        """Retourne les aliments dont la DLC arrive dans les `days` prochains jours."""
        limit = date.today() + timedelta(days=days)
        result = []
        for item in self._items.values():
            exp = item.get("expiration_date")
            if not exp:
                continue
            try:
                exp_date = date.fromisoformat(exp)
            except ValueError:
                continue
            if exp_date <= limit:
                result.append(item)
        return sorted(result, key=lambda i: i["expiration_date"])

    async def async_add_item(
        self,
        name: str,
        quantity: float,
        unit: str,
        expiration_date: str,
    ) -> str:
        """Ajoute un aliment au stock et retourne son identifiant.

        La DLC est obligatoire (voir ADD_ITEM_SCHEMA cote __init__.py) : le
        principe du projet est de prioriser l'anti-gaspi par date de
        peremption, ce qui ne fonctionne que si chaque aliment en a une.
        """
        item_id = uuid.uuid4().hex[:8]
        self._items[item_id] = {
            "id": item_id,
            "name": name,
            "quantity": quantity,
            "unit": unit,
            "expiration_date": expiration_date,
            "added_at": datetime.now().isoformat(),
        }
        await self._async_save()
        _LOGGER.debug("Aliment ajoute au stock: %s", self._items[item_id])
        return item_id

    async def async_update_item(
            self,
            item_id: str,
            name: str | None = None,
            quantity: float | None = None,
            unit: str | None = None,
            expiration_date: str | None = None,
        ) -> bool:
        """Met a jour un aliment existant. Retourne False si introuvable."""
        if item_id not in self._items:
            return False
        item = self._items[item_id]
        if name is not None:
            item["name"] = name
        if quantity is not None:
            item["quantity"] = quantity
        if unit is not None:
            item["unit"] = unit
        if expiration_date is not None:
            item["expiration_date"] = expiration_date
        await self._async_save()
        _LOGGER.debug("Aliment mis a jour: %s", item)
        return True

        async def async_remove_item(self, item_id: str) -> bool:
        """Supprime un aliment du stock. Retourne False si introuvable."""
        if item_id not in self._items:
            return False
        del self._items[item_id]
        await self._async_save()
        return True
