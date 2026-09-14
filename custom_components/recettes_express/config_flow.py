"""Config flow pour Recettes Express."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_GEMINI_API_KEY, DEFAULT_NAME, DOMAIN, GEMINI_API_BASE, GEMINI_TEXT_MODEL

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({vol.Required(CONF_GEMINI_API_KEY): str})


async def _async_validate_api_key(hass: HomeAssistant, api_key: str) -> tuple[bool, str | None]:
    """Fait un appel minimal a Gemini pour verifier que la cle est valide.

    Retourne (succes, code_erreur). code_erreur vaut "invalid_auth" si Gemini
    rejette explicitement la cle, "quota_exceeded" si le compte a deja
    epuise son quota gratuit du jour (la cle est valide, mais on ne peut
    pas encore le confirmer par un appel reussi), sinon "cannot_connect"
    pour toute autre erreur (mauvais modele, API non activee, reseau...).
    """
    session = async_get_clientsession(hass)
    url = f"{GEMINI_API_BASE}/{GEMINI_TEXT_MODEL}:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": "ping"}]}]}

    async with session.post(url, json=payload) as resp:
        if resp.status == 200:
            return True, None

        body = await resp.text()
        _LOGGER.error(
            "Validation de la cle Gemini echouee (HTTP %s): %s", resp.status, body
        )
        if resp.status in (400, 401, 403):
            return False, "invalid_auth"
        if resp.status == 429:
            return False, "quota_exceeded"
        return False, "cannot_connect"


class RecettesExpressConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gere le flux de configuration initial."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            try:
                valid, error_code = await _async_validate_api_key(
                    self.hass, user_input[CONF_GEMINI_API_KEY]
                )
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Erreur lors de la validation de la cle Gemini")
                errors["base"] = "cannot_connect"
            else:
                if not valid:
                    errors["base"] = error_code
                else:
                    return self.async_create_entry(title=DEFAULT_NAME, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
