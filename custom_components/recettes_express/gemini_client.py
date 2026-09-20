"""Client REST minimal pour l'API Gemini (vision + texte)."""
from __future__ import annotations

import base64
import json
import logging
import re
import unicodedata
from datetime import date
from typing import Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.core import HomeAssistant

from .categorize import guess_category, is_valid_category
from .const import GEMINI_API_BASE, GEMINI_TEXT_MODEL, GEMINI_VISION_MODEL, UNITS

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
     "expiration_date": "YYYY-MM-DD ou null",
     "category": "une valeur parmi fruits_legumes, viandes_poissons, produits_laitiers, boissons, epicerie, autres"}}
  ]
}}
Les unites valides sont: g, kg, ml, l, piece, boite, paquet. Si tu ne peux pas estimer
la quantite, mets 1 avec l'unite "piece". Pour la categorie, choisis la plus
appropriee dans la liste ci-dessus ; utilise "autres" si aucune ne convient clairement."""

VOICE_RECOGNITION_PROMPT_TEMPLATE = """Nous sommes le {today}. Tu ecoutes un enregistrement audio en francais
dans lequel une personne enonce a voix haute un ou plusieurs aliments qu'elle vient d'acheter
ou de ranger dans son stock, generalement avec la quantite et parfois la date de peremption.
Identifie chaque aliment mentionne.

Pour la date de peremption (DLC/DDM) de chaque aliment :
- Si une date est explicitement mentionnee dans l'audio, utilise-la (convertis-la au format
  YYYY-MM-DD, en te basant sur l'annee en cours si elle n'est pas precisee).
- Si aucune date n'est mentionnee, NE METS PAS null : estime plutot une date de peremption
  raisonnable a partir d'aujourd'hui, en te basant sur la duree de conservation typique de cet
  aliment a temperature ambiante ou au frigo selon ce qui est le plus probable.

Si la quantite n'est pas mentionnee, utilise 1. Si l'unite n'est pas mentionnee, utilise "piece".
Pour la categorie, choisis la plus appropriee parmi : fruits_legumes, viandes_poissons,
produits_laitiers, surgeles, pain_boulangerie, condiments_epices, boissons, epicerie, autres.

Reponds UNIQUEMENT avec un JSON valide (pas de texte autour, pas de markdown), au format :
{{
  "items": [
    {{"name": "nom de l'aliment", "quantity": 1, "unit": "piece",
     "expiration_date": "YYYY-MM-DD ou null",
     "categorie": "une valeur parmi fruits_legumes|viandes_poissons|produits_laitiers|surgeles|pain_boulangerie|condiments_epices|boissons|epicerie|autres"}}
  ]
}}
Si aucun aliment n'est identifiable dans l'audio, reponds avec {{"items": []}}."""

RECIPE_PROMPT_TEMPLATE = """Tu es un assistant culinaire oriente anti-gaspillage. Voici la
liste EXHAUSTIVE des aliments actuellement disponibles, avec leur identifiant interne, leur
quantite et leur date de peremption quand elle est connue :

{stock_list}

REGLE ABSOLUE (la plus importante de toutes) : tu ne dois utiliser ET ne mentionner, ni dans
"used_item_ids" ni dans le texte des "steps", AUCUN aliment absent de la liste ci-dessus, a
la seule exception de ces bases de cuisine courantes : sel, poivre, sucre, epices,
eau. N'ajoute JAMAIS d'autres ingredients (par exemple : ail, oignon, fromage,
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
{extra_consignes}
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
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as err:
        raise GeminiError(f"Reponse Gemini non-JSON: {err}") from err
    if not isinstance(parsed, dict):
        raise GeminiError(f"Reponse Gemini n'est pas un objet JSON: {parsed!r}")
    return parsed


def _coerce_str(value: Any, default: str = "") -> str:
    """Convertit une valeur JSON quelconque en chaine, sans jamais lever."""
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return default
    return str(value).strip()


def _coerce_number(value: Any, default: float = 1.0) -> float:
    """Convertit une valeur JSON quelconque en nombre, sans jamais lever."""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_detected_items(raw: Any) -> list[dict[str, Any]]:
    """Valide et normalise les aliments detectes par Gemini.

    Gemini est un LLM : rien ne garantit que sa reponse respecte le schema
    demande dans le prompt (champ manquant, mauvais type, unite invalide...).
    On ne fait jamais confiance aveuglement au JSON recu - chaque entree est
    validee et normalisee, ou ignoree si elle n'est pas exploitable, plutot
    que de laisser une donnee incorrecte remonter jusqu'au stock ou a la carte.
    """
    if not isinstance(raw, list):
        _LOGGER.warning("Reponse Gemini 'items' inattendue (pas une liste): %r", raw)
        return []

    items: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = _coerce_str(entry.get("name"))
        if not name:
            continue
        unit = _coerce_str(entry.get("unit"), "piece")
        if unit not in UNITS:
            unit = "piece"
        expiration_date = entry.get("expiration_date")
        if not isinstance(expiration_date, str) or not expiration_date.strip():
            expiration_date = None
        category = entry.get("category")
        if not isinstance(category, str) or not is_valid_category(category):
            category = guess_category(name)
        items.append(
            {
                "name": name,
                "quantity": _coerce_number(entry.get("quantity"), 1.0),
                "unit": unit,
                "expiration_date": expiration_date,
                "category": category,
            }
        )
    return items


def _normalize_text_for_matching(value: str) -> str:
    """Minuscule et sans accents, pour reperer un mot quel que soit son accent."""
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


# Ingredients frequemment "invente" par le modele dans le texte des etapes
# alors qu'ils sont absents du stock et des bases de cuisine autorisees
# (voir RECIPE_PROMPT_TEMPLATE) - constate en usage reel (ex: ajout de
# parmesan ou de vinaigre non demande). Deuxieme barriere cote code : la
# consigne du prompt seule ne suffit pas toujours a l'empecher.
_HALLUCINATION_WATCHLIST = [
    "fromage", "parmesan", "parmigiano", "mozzarella", "gruyere", "emmental",
    "comte", "chevre", "feta", "cheddar", "creme", "beurre", "ail", "oignon",
    "echalote", "bouillon", "citron", "vinaigre", "moutarde", "mayonnaise",
    "miel", "chocolat", "amande", "noix", "olive", "persil", "basilic",
    "coriandre", "thym", "romarin", "laurier", "ciboulette", "soja", "vin",
]


def _find_hallucinated_ingredients(steps: list[str], stock_names: list[str]) -> list[str]:
    """Detecte les mots de _HALLUCINATION_WATCHLIST mentionnes dans les etapes
    mais absents des noms d'aliments du stock fourni."""
    normalized_stock = _normalize_text_for_matching(" ".join(stock_names))
    normalized_steps = _normalize_text_for_matching(" ".join(steps))
    found = []
    for word in _HALLUCINATION_WATCHLIST:
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, normalized_steps) and not re.search(pattern, normalized_stock):
            found.append(word)
    return found


def _normalize_recipes(
    raw: Any,
    valid_item_ids: set[str] | None = None,
    stock_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Valide et normalise les recettes proposees par Gemini.

    En plus de la validation de type (meme raison que _normalize_detected_items),
    filtre used_item_ids pour ne garder que des identifiants qui existent
    vraiment dans le stock fourni, et rejette toute recette dont le texte des
    etapes mentionne un ingredient de _HALLUCINATION_WATCHLIST absent du
    stock : deux barrieres cote code (en plus de la regle dans le prompt)
    contre un ingredient invente qui se retrouverait quand meme dans la
    reponse.
    """
    if not isinstance(raw, list):
        _LOGGER.warning("Reponse Gemini 'recipes' inattendue (pas une liste): %r", raw)
        return []

    recipes: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        title = _coerce_str(entry.get("title"))
        if not title:
            continue
        used_ids_raw = entry.get("used_item_ids")
        used_ids = (
            [str(i) for i in used_ids_raw if isinstance(i, (str, int)) and not isinstance(i, bool)]
            if isinstance(used_ids_raw, list)
            else []
        )
        if valid_item_ids is not None:
            used_ids = [i for i in used_ids if i in valid_item_ids]
        steps_raw = entry.get("steps")
        steps = (
            [s for s in (_coerce_str(step) for step in steps_raw) if s]
            if isinstance(steps_raw, list)
            else []
        )
        if not steps:
            continue
        if stock_names is not None:
            hallucinated = _find_hallucinated_ingredients(steps, stock_names)
            if hallucinated:
                _LOGGER.warning(
                    "Recette '%s' rejetee : ingredient(s) hors stock detecte(s) dans "
                    "les etapes (%s)",
                    title,
                    ", ".join(hallucinated),
                )
                continue
        recipes.append(
            {
                "title": title,
                "used_item_ids": used_ids,
                "prep_minutes": _coerce_number(entry.get("prep_minutes"), 0),
                "steps": steps,
            }
        )
    return recipes


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
        return _normalize_detected_items(result.get("items"))

    async def recognize_food_from_voice(
        self, audio_bytes: bytes, mime_type: str = "audio/webm"
    ) -> list[dict[str, Any]]:
        """Envoie un enregistrement audio a Gemini et retourne une liste d'aliments detectes."""
        b64_audio = base64.b64encode(audio_bytes).decode("ascii")
        prompt = VOICE_RECOGNITION_PROMPT_TEMPLATE.format(today=date.today().isoformat())
        parts = [
            {"text": prompt},
            {"inline_data": {"mime_type": mime_type, "data": b64_audio}},
        ]
        # "minimal" convient bien ici aussi : extraction directe depuis l'audio,
        # pas de raisonnement complexe necessaire.
        text = await self._generate(GEMINI_VISION_MODEL, parts, thinking_level="minimal")
        result = _extract_json(text)
        return _normalize_detected_items(result.get("items"))

    async def suggest_recipes(
        self,
        stock_items: list[dict[str, Any]],
        max_recipes: int = 3,
        servings: int | None = None,
        vegetarian: bool = False,
        max_prep_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """Demande a Gemini de proposer des recettes a partir du stock fourni."""
        stock_list = "\n".join(
            f"- [{i['id']}] {i['name']}: {i['quantity']} {i['unit']}"
            + (f" (DLC: {i['expiration_date']})" if i.get("expiration_date") else "")
            for i in stock_items
        ) or "(stock vide)"

        extra_lines = []
        if servings:
            extra_lines.append(f"- Prevois les quantites pour {servings} personne(s).")
        if vegetarian:
            extra_lines.append(
                "- Ne propose que des recettes vegetariennes (sans viande ni poisson)."
            )
        if max_prep_minutes:
            extra_lines.append(
                f"- Le temps de preparation total ne doit pas depasser {max_prep_minutes} minutes."
            )
        extra_consignes = ("\n".join(extra_lines) + "\n") if extra_lines else ""

        prompt = RECIPE_PROMPT_TEMPLATE.format(
            stock_list=stock_list,
            max_recipes=max_recipes,
            extra_consignes=extra_consignes,
        )
        text = await self._generate(GEMINI_TEXT_MODEL, [{"text": prompt}], thinking_level="low")
        result = _extract_json(text)
        valid_ids = {
            str(i["id"]) for i in stock_items if isinstance(i, dict) and "id" in i
        }
        stock_names = [
            i["name"] for i in stock_items if isinstance(i, dict) and isinstance(i.get("name"), str)
        ]
        return _normalize_recipes(result.get("recipes"), valid_ids, stock_names)
