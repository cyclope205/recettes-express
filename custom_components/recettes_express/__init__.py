"""Integration Recettes Express."""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components import frontend
from homeassistant.components.camera import async_get_image as camera_async_get_image

try:
    from homeassistant.components.http import StaticPathConfig
except ImportError:  # Home Assistant anterieur a 2024.7
    StaticPathConfig = None
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_call_later

from .const import (
    ATTR_CAMERA_ENTITY_ID,
    ATTR_EXPIRATION_DATE,
    ATTR_IMAGE_BASE64,
    ATTR_IMAGE_PATH,
    ATTR_ITEM_ID,
    ATTR_ITEM_IDS,
    ATTR_MAX_RECIPES,
    ATTR_NAME,
    ATTR_QUANTITY,
    ATTR_RECIPE_INDEX,
    ATTR_UNIT,
    CONF_GEMINI_API_KEY,
    DATA_LAST_SUGGESTIONS,
    DOMAIN,
    SERVICE_ACCEPT_RECIPE,
    SERVICE_ADD_ITEM,
    SERVICE_ADD_ITEM_FROM_PHOTO,
    SERVICE_REMOVE_ITEM,
    SERVICE_SUGGEST_RECIPES,
    UNITS,
)
from .gemini_client import GeminiClient, GeminiError
from .storage import StockManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

CARD_URL_PATH = "/recettes_express_files"
CARD_JS_FILENAME = "recettes-express-card.js"
_MANIFEST_PATH = Path(__file__).parent / "manifest.json"
CARD_VERSION = json.loads(_MANIFEST_PATH.read_text())["version"]

ADD_ITEM_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_NAME): cv.string,
        vol.Required(ATTR_QUANTITY): vol.Coerce(float),
        vol.Required(ATTR_UNIT): vol.In(UNITS),
        vol.Required(ATTR_EXPIRATION_DATE): cv.string,
    }
)

REMOVE_ITEM_SCHEMA = vol.Schema({vol.Required(ATTR_ITEM_ID): cv.string})

ADD_ITEM_FROM_PHOTO_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_IMAGE_PATH): cv.string,
        vol.Optional(ATTR_IMAGE_BASE64): cv.string,
        vol.Optional(ATTR_CAMERA_ENTITY_ID): cv.entity_id,
    }
)

SUGGEST_RECIPES_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ITEM_IDS): [cv.string],
        vol.Optional(ATTR_MAX_RECIPES, default=3): vol.Coerce(int),
    }
)

ACCEPT_RECIPE_SCHEMA = vol.Schema({vol.Required(ATTR_RECIPE_INDEX): vol.Coerce(int)})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialise l'integration a partir d'une entree de configuration."""
    hass.data.setdefault(DOMAIN, {})

    stock = StockManager(hass)
    await stock.async_load()

    gemini = GeminiClient(hass, entry.data[CONF_GEMINI_API_KEY])

    hass.data[DOMAIN][entry.entry_id] = {
        "stock": stock,
        "gemini": gemini,
        DATA_LAST_SUGGESTIONS: [],
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass, entry)

    try:
        await _async_register_frontend_card(hass)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception(
            "Impossible d'enregistrer automatiquement la carte Lovelace "
            "(l'integration reste fonctionnelle, mais il faudra l'ajouter "
            "manuellement en ressource)"
        )

    return True


async def _async_register_frontend_card(hass: HomeAssistant) -> None:
    """Sert le fichier de la carte Lovelace et l'enregistre automatiquement."""
    if hass.data[DOMAIN].get("_frontend_registered"):
        return

    www_path = Path(__file__).parent / "www"
    if not www_path.is_dir():
        _LOGGER.warning(
            "Dossier 'www' introuvable (%s) : la carte Lovelace ne sera pas "
            "servie automatiquement.",
            www_path,
        )
        return

    js_url = f"{CARD_URL_PATH}/{CARD_JS_FILENAME}?v={CARD_VERSION}"

    try:
        if StaticPathConfig is None:
            raise AttributeError
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_PATH, str(www_path), cache_headers=True)]
        )
    except AttributeError:
        hass.http.register_static_path(CARD_URL_PATH, str(www_path), cache_headers=True)

    hass.data[DOMAIN]["_frontend_registered"] = True
    hass.data[DOMAIN]["_card_js_url"] = js_url
    await _async_sync_lovelace_resource(hass)
    _LOGGER.debug("Carte Lovelace Recettes Express servie automatiquement depuis %s", js_url)


async def _async_sync_lovelace_resource(hass: HomeAssistant, _now=None) -> None:
    """Enregistre la carte comme une vraie ressource Lovelace (la methode normale)."""
    js_url = hass.data[DOMAIN]["_card_js_url"]
    lovelace_data = hass.data.get("lovelace")
    resources = getattr(lovelace_data, "resources", None)
    if resources is None:
        _LOGGER.debug("Lovelace pas encore pret, nouvel essai dans 5s")
        async_call_later(hass, 5, _async_sync_lovelace_resource)
        return

    if not hasattr(resources, "async_create_item"):
        _LOGGER.warning(
            "Les ressources Lovelace sont en mode YAML ; la carte ne peut "
            "pas etre enregistree automatiquement comme une ressource "
            "propre. Utilisation d'add_extra_js_url en secours."
        )
        frontend.add_extra_js_url(hass, js_url)
        return

    try:
        if not getattr(resources, "loaded", False):
            await resources.async_load()

        existing = next(
            (
                item
                for item in resources.async_items()
                if str(item.get("url", "")).split("?", 1)[0] == CARD_URL_PATH + "/" + CARD_JS_FILENAME
            ),
            None,
        )
        if existing is None:
            await resources.async_create_item({"res_type": "module", "url": js_url})
        elif existing.get("url") != js_url:
            await resources.async_update_item(existing["id"], {"url": js_url})
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "Impossible d'enregistrer automatiquement la ressource Lovelace "
            "pour la carte ; utilisation d'add_extra_js_url en secours.",
            exc_info=True,
        )
        frontend.add_extra_js_url(hass, js_url)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Decharge l'entree de configuration."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


def _get_entry_data(hass: HomeAssistant) -> dict:
    """Recupere les donnees de la (premiere) entree configuree."""
    entries_data = hass.data.get(DOMAIN, {})
    for key, value in entries_data.items():
        if isinstance(key, str) and key.startswith("_"):
            continue
        return value
    raise HomeAssistantError("Recettes Express n'est pas configure")


def _async_register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Enregistre les services (une seule fois pour tout le domaine)."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_ITEM):
        return

    async def handle_add_item(call: ServiceCall) -> None:
        data = _get_entry_data(hass)
        stock: StockManager = data["stock"]
        await stock.async_add_item(
            name=call.data[ATTR_NAME],
            quantity=call.data[ATTR_QUANTITY],
            unit=call.data[ATTR_UNIT],
            expiration_date=call.data[ATTR_EXPIRATION_DATE],
        )

    async def handle_remove_item(call: ServiceCall) -> None:
        data = _get_entry_data(hass)
        stock: StockManager = data["stock"]
        removed = await stock.async_remove_item(call.data[ATTR_ITEM_ID])
        if not removed:
            raise HomeAssistantError(f"Aliment {call.data[ATTR_ITEM_ID]} introuvable")

    async def handle_add_item_from_photo(call: ServiceCall) -> ServiceResponse:
        data = _get_entry_data(hass)
        gemini: GeminiClient = data["gemini"]

        image_bytes: bytes | None = None
        image_path = call.data.get(ATTR_IMAGE_PATH)
        image_base64 = call.data.get(ATTR_IMAGE_BASE64)
        camera_entity_id = call.data.get(ATTR_CAMERA_ENTITY_ID)

        if image_base64:
            if "," in image_base64[:64]:
                image_base64 = image_base64.split(",", 1)[1]
            try:
                image_bytes = base64.b64decode(image_base64)
            except (ValueError, TypeError) as err:
                raise HomeAssistantError(f"Image base64 invalide: {err}") from err
        elif image_path:
            if not await hass.async_add_executor_job(
                lambda: hass.config.is_allowed_path(image_path)
            ):
                raise HomeAssistantError(f"Chemin non autorise: {image_path}")

            def _read_file() -> bytes:
                with open(image_path, "rb") as file:
                    return file.read()

            image_bytes = await hass.async_add_executor_job(_read_file)
        elif camera_entity_id:
            image = await camera_async_get_image(hass, camera_entity_id)
            image_bytes = image.content
        else:
            raise HomeAssistantError(
                f"Fournir '{ATTR_IMAGE_BASE64}', '{ATTR_IMAGE_PATH}' ou '{ATTR_CAMERA_ENTITY_ID}'"
            )

        try:
            detected_items = await gemini.recognize_food(image_bytes)
        except GeminiError as err:
            raise HomeAssistantError(f"Reconnaissance IA impossible: {err}") from err

        return {"detected_items": detected_items}

    async def handle_suggest_recipes(call: ServiceCall) -> ServiceResponse:
        data = _get_entry_data(hass)
        stock: StockManager = data["stock"]
        gemini: GeminiClient = data["gemini"]

        max_recipes = call.data[ATTR_MAX_RECIPES]
        item_ids = call.data.get(ATTR_ITEM_IDS)
        if item_ids:
            items = stock.get_items_by_ids(item_ids)
            if not items:
                raise HomeAssistantError(
                    "Aucun des aliments selectionnes n'a ete trouve dans le "
                    "stock (a-t-il ete supprime entre-temps ?)"
                )
        else:
            items = stock.get_items()

        try:
            recipes = await gemini.suggest_recipes(items, max_recipes=max_recipes)
        except GeminiError as err:
            raise HomeAssistantError(f"Suggestion de recettes impossible: {err}") from err

        data[DATA_LAST_SUGGESTIONS] = recipes
        return {"recipes": recipes}

    async def handle_accept_recipe(call: ServiceCall) -> ServiceResponse:
        data = _get_entry_data(hass)
        stock: StockManager = data["stock"]
        suggestions = data.get(DATA_LAST_SUGGESTIONS, [])

        index = call.data[ATTR_RECIPE_INDEX]
        if index < 0 or index >= len(suggestions):
            raise HomeAssistantError("Index de recette invalide (relancez suggest_recipes)")

        recipe = suggestions[index]
        removed_count = 0
        for item_id in recipe.get("used_item_ids", []):
            if await stock.async_remove_item(item_id):
                removed_count += 1

        return {"accepted": recipe["title"], "removed_count": removed_count}

    hass.services.async_register(DOMAIN, SERVICE_ADD_ITEM, handle_add_item, schema=ADD_ITEM_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_REMOVE_ITEM, handle_remove_item, schema=REMOVE_ITEM_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_ITEM_FROM_PHOTO,
        handle_add_item_from_photo,
        schema=ADD_ITEM_FROM_PHOTO_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SUGGEST_RECIPES,
        handle_suggest_recipes,
        schema=SUGGEST_RECIPES_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ACCEPT_RECIPE,
        handle_accept_recipe,
        schema=ACCEPT_RECIPE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
