"""Client REST minimal pour l'API Gemini (vision + texte)."""
from __future__ import annotations

import base64
import json
import logging
from datetime import date
from typing import Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.core import HomeAssistant

from .const import GEMINI_API_BASE, GEMINI_TEXT_MODEL, GEMINI_VISION_MODEL

_LOGGER = logging.getLogger(__name__)

RECOGNITION_PROMPT_TEMPLATE = """Nous sommes le {today}. Tu regardes une photo d'un ou plusieurs
aliments, potentiellement avec leur emballage. Identifie chaque aliment visible.

Pour la date de peremption (DLC/DDM) de chaque aliment :
- Si une date est imprimee et lisible sur l'emballage, utilise-la telle quelle.
- Sinon (cas frequent pour un fruit, un legume, ou tout produit frais sans emballage),
  NE METS PAS null : estime plutot une date de peremption raisonnable a partir
  d'aujourd'hui, en te basant sur la duree de conservation typique de cet aliment a
  temperature ambiante ou au frigo selon ce qui est le plus probable (par exemple une
  banane mure se garde quelques jours, une carotte plusieurs semaines). Ce n'est qu'une
  estimation que l'utilisateur pourra corriger, mieux vaut une estimation raisonnable
  qu'une absence de date.
- Ne mets null que si l'aliment lui-meme est ambigu au point de ne pouvoir rien estimer.

Reponds UNIQUEMENT avec un JSON valide (pas de texte autour, pas de markdown), au format :
{{
  "items": [
    {{"name": "nom de l'aliment", "quantity": 1, "unit": "piece",
     "expiration_date": "YYYY-MM-DD ou null"}}
  ]
}}
Les unites valides sont: g, kg, ml, l, piece, boite, paquet. Si tu ne peux pas estimer
la quantite, mets 1 avec l'unite "piece"."""

RECIPE_PROMPT_TEMPLATE = """Tu es un assistant culinaire oriente anti-gaspillage. Voici la
liste EXHAUSTIVE des aliments actuellement disponibles, avec leur identifiant interne, leur
quantite et leur date de peremption quand elle est connue :

{stock_list}

REGLE ABSOLUE (la plus importante de toutes) : tu ne dois utiliser ET ne mentionner, ni dans
"used_item_ids" ni dans le texte des "steps", AUCUN aliment absent de la liste ci-dessus, a
la seule exception de ces bases de cuisine courantes : sel, poivre, sucre, epices, huile, beurre,
eau, farine. N'ajoute JAMAIS d'autres ingredients (par exemple : ail, oignon, fromage,
creme, herbes fraiches, bouillon, citron, sauce soja...) meme si la recette serait meilleure
avec, sauf s'ils figurent explicitement dans la liste ci-dessus.

Propose {max_recipes} recette(s) realisables prioritairement avec les aliments dont la DLC
est la plus proche, pour eviter le gaspillage. Priorise les aliments qui risqueraient sinon
d'etre jetes avant d'etre utilises.

Consignes :
- Varie les recettes entre elles (types de plats, styles de cuisine) plutot que de proposer
plusieurs recettes tres similaires (par exemple, evite de proposer plusieurs salades ou
plusieurs soupes a la suite si d'autres options raisonnables existent).
- Les recettes n'ont pas besoin d'utiliser tous les aliments de la liste, mais doivent rester
realistes avec les quantites reellement disponibles (ne prevois pas plus d'un aliment que sa
quantite indiquee ne le permet).
- Redige des etapes concretes et actionnables (entre 3 et 8 etapes par recette), pour
quelqu'un qui cuisine chez lui avec du materiel standard.
- Indique un temps de preparation total approximatif en minutes.

Avant de repondre, relis chaque etape de chaque recette une par une et verifie qu'aucun
ingredient mentionne n'est absent de la liste des aliments disponibles ou des bases de
cuisine autorisees listees ci-dessus. Si c'est le cas, corrige ou reformule l'etape pour
retirer cet ingredient avant de repondre.

Pour chaque recette, indique quels aliments de la liste sont utilises en donnant leur
identifiant EXACT (le code entre crochets, pas leur nom) dans "used_item_ids".

Reponds UNIQUEMENT avec un JSON valide (pas de texte autour, pas de markdown), au format :
{{
"recipes": [
{{
"title": "Nom de la recette",
"used_item_ids": ["id1", "id2"],
"prep_minutes": 20,
"steps": ["Etape 1...", "Etape 2..."]
}}
]
}}"""
class GeminiError(Exception):
    """Erreur lors d'un appel a l'API Gemini."""


class GeminiQuotaError(GeminiError):
    """Le quota gratuit journalier/par minute de l'API Gemini est atteint."""


def _extract_json(text: str) -> dict[str, Any]:
    """Extrait un objet JSON d'une reponse texte (tolere les blocs ```json)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as err:
        raise GeminiError(f"Reponse Gemini non-JSON: {err}") from err


class GeminiClient:
    """Petit wrapper autour de l'API generativelanguage de Google."""

    def __init__(self, hass: HomeAssistant, api_key: str) -> None:
        self._hass = hass
        self._api_key = api_key
        self._session = async_get_clientsession(hass)

    async def _generate(
        self, model: str, parts: list[dict[str, Any]], thinking_level: str = "low"
    ) -> str:
        url = f"{GEMINI_API_BASE}/{model}:generateContent?key={self._api_key}"
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                # "minimal"/"low" reduit la latence sur des taches directes
                # (extraction, classement) qui ne demandent pas un
                # raisonnement multi-etapes - voir gemini_client.recognize_food.
                "thinkingConfig": {"thinkingLevel": thinking_level},
            },
        }
        async with self._session.post(url, json=payload) as resp:
            if resp.status == 429:
                retry_delay = None
                try:
                    body = await resp.json()
                    for detail in body.get("error", {}).get("details", []):
                        if detail.get("@type", "").endswith("RetryInfo"):
                            retry_delay = detail.get("retryDelay")
                except (json.JSONDecodeError, AttributeError):
                    pass
                msg = "Quota Gemini atteint pour l'instant."
                if retry_delay:
                    msg += f" Reessayez dans {retry_delay}."
                else:
                    msg += " Reessayez plus tard (le quota gratuit se reinitialise chaque jour)."
                raise GeminiQuotaError(msg)
            if resp.status != 200:
                body = await resp.text()
                _LOGGER.error("Erreur API Gemini (%s): %s", resp.status, body)
                raise GeminiError(f"Erreur API Gemini (HTTP {resp.status})")
            data = await resp.json()

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as err:
            raise GeminiError(f"Reponse Gemini inattendue: {data}") from err

    async def recognize_food(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> list[dict[str, Any]]:
        """Envoie une photo a Gemini et retourne une liste d'aliments detectes."""
        b64_image = base64.b64encode(image_bytes).decode("ascii")
        prompt = RECOGNITION_PROMPT_TEMPLATE.format(today=date.today().isoformat())
        parts = [
            {"text": prompt},
            {"inline_data": {"mime_type": mime_type, "data": b64_image}},
        ]
        # "minimal" (le niveau le plus bas disponible) convient bien a une
        # tache d'extraction directe comme celle-ci - identifier des
        # aliments visibles et lire/estimer une date ne demande pas de
        # raisonnement multi-etapes.
        text = await self._generate(GEMINI_VISION_MODEL, parts, thinking_level="minimal")
        result = _extract_json(text)
        return result.get("items", [])

    async def suggest_recipes(
        self, stock_items: list[dict[str, Any]], max_recipes: int = 3
    ) -> list[dict[str, Any]]:
        """Demande a Gemini de proposer des recettes a partir du stock fourni."""
        stock_list = "\n".join(
            f"- [{i['id']}] {i['name']}: {i['quantity']} {i['unit']}"
            + (f" (DLC: {i['expiration_date']})" if i.get("expiration_date") else "")
            for i in stock_items
        ) or "(stock vide)"

        prompt = RECIPE_PROMPT_TEMPLATE.format(stock_list=stock_list, max_recipes=max_recipes)
        text = await self._generate(GEMINI_TEXT_MODEL, [{"text": prompt}], thinking_level="low")
        result = _extract_json(text)
        return result.get("recipes", [])
