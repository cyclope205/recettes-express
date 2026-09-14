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
    SUGGESTIONS_STORAGE_KEY,
)

_LOGGER = logging.getLogger(__name__)


class StockManager:
    """Charge, modifie et persiste la liste des aliments en stock."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._items: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        """Charge le stock depuis le disque.

        Le fichier de stockage n'est pas garanti d'etre dans le format
        attendu (ancienne version, edition manuelle, corruption disque...).
        On valide chaque entree plutot que de faire confiance aveuglement
        au contenu charge : une entree invalide est ignoree (avec un
        avertissement) au lieu de planter ou de propager des donnees
        incoherentes au reste de l'integration.
        """
        data = await self._store.async_load()
        raw_items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(raw_items, dict):
            if data is not None:
                _LOGGER.warning(
                    "Stock enregistre dans un format inattendu ; demarrage avec un stock vide."
                )
            self._items = {}
            return

        items: dict[str, dict[str, Any]] = {}
        for item_id, item in raw_items.items():
            if not isinstance(item_id, str) or not isinstance(item, dict):
                continue
            name = item.get("name")
            unit = item.get("unit")
            if not isinstance(name, str) or not name:
                continue
            if not isinstance(unit, str) or not unit:
                continue
            quantity = item.get("quantity")
            if not isinstance(quantity, (int, float)) or isinstance(quantity, bool):
                quantity = 1
            expiration_date = item.get("expiration_date")
            if not isinstance(expiration_date, str) or not expiration_date:
                expiration_date = None
            items[item_id] = {
                "id": item.get("id", item_id),
                "name": name,
                "quantity": quantity,
                "unit": unit,
                "expiration_date": expiration_date,
                "added_at": item.get("added_at"),
            }

        if len(items) != len(raw_items):
            _LOGGER.warning(
                "%d entree(s) du stock ignorees au chargement (format invalide).",
                len(raw_items) - len(items),
            )
        self._items = items

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



class SuggestionsStore:
    """Persiste les dernieres recettes suggerees par Gemini.

    Sans cela, accept_recipe dependait uniquement d'une liste gardee en
    memoire (hass.data) : un redemarrage de Home Assistant entre une
    suggestion et sa validation faisait perdre les recettes proposees,
    obligeant a relancer un appel Gemini pour rien.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, SUGGESTIONS_STORAGE_KEY)
        self._recipes: list[dict[str, Any]] = []

    async def async_load(self) -> None:
        """Charge les dernieres suggestions depuis le disque."""
        data = await self._store.async_load()
        recipes = data.get("recipes") if isinstance(data, dict) else None
        self._recipes = recipes if isinstance(recipes, list) else []

    def get(self) -> list[dict[str, Any]]:
        """Retourne les dernieres recettes suggerees (liste vide si aucune)."""
        return self._recipes

    async def async_set(self, recipes: list[dict[str, Any]]) -> None:
        """Remplace et persiste les dernieres recettes suggerees."""
        self._recipes = recipes
        await self._store.async_save({"recipes": recipes})
