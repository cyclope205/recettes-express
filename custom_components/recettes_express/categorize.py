"""Classement automatique des aliments par categorie, par mots-cles.

Utilise pour les aliments ajoutes manuellement (pas de vision IA pour deviner
une categorie) et en repli quand Gemini ne renvoie pas de categorie valide
pour un aliment detecte par photo (voir gemini_client._normalize_detected_items).

Volontairement simple (mots-cles, pas d'IA) : rapide, gratuit, et suffisant
pour du rangement indicatif dans la carte. DEFAULT_CATEGORY ("autres") est le
repli des qu'aucun mot-cle ne correspond, plutot que de deviner au hasard.
"""
from __future__ import annotations

import unicodedata

from .const import CATEGORIES, DEFAULT_CATEGORY

# L'ordre des categories determine la priorite en cas de mot-cle ambigu
# (ex. "lait" est dans produits_laitiers, pas boissons, car verifie avant).
_KEYWORDS: dict[str, list[str]] = {
    "fruits_legumes": [
        "pomme", "poire", "banane", "orange", "citron", "fraise", "framboise",
        "raisin", "peche", "abricot", "prune", "cerise", "melon", "pasteque",
        "kiwi", "mangue", "ananas", "avocat", "tomate", "carotte", "courgette",
        "aubergine", "poivron", "concombre", "salade", "laitue", "epinard",
        "brocoli", "chou", "haricot", "petit pois", "pomme de terre", "patate",
        "oignon", "ail", "echalote", "poireau", "champignon", "betterave",
        "radis", "navet", "celeri", "fenouil", "artichaut", "asperge",
        "courge", "potiron", "citrouille", "persil", "basilic", "coriandre",
        "ciboulette", "menthe", "gingembre",
    ],
    "viandes_poissons": [
        "poulet", "boeuf", "porc", "agneau", "veau", "dinde", "canard",
        "lapin", "saucisse", "saucisson", "jambon", "lardons", "bacon",
        "steak", "cote de", "entrecote", "merguez", "chorizo", "pate de",
        "poisson", "saumon", "thon", "cabillaud", "truite", "sardine",
        "crevette", "moule", "huitre", "calamar", "crabe", "homard",
        "oeuf", "oeufs",
    ],
    "produits_laitiers": [
        "lait", "yaourt", "yogourt", "fromage", "creme", "beurre",
        "parmesan", "mozzarella", "emmental", "gruyere", "comte", "chevre",
        "feta", "cheddar", "camembert", "brie", "ricotta", "mascarpone",
        "petit suisse",
    ],
    "boissons": [
        "eau", "jus", "soda", "the", "cafe", "vin", "biere", "limonade",
        "sirop", "smoothie", "cidre", "champagne", "tisane",
    ],
    "epicerie": [
        "riz", "pates", "pate", "farine", "sucre", "sel", "poivre", "huile",
        "vinaigre", "moutarde", "mayonnaise", "ketchup", "sauce", "conserve",
        "bouillon", "epice", "cereale", "biscuit", "chocolat", "confiture",
        "miel", "pain", "levure", "lentille", "pois chiche", "quinoa",
        "semoule", "gateau", "gaufre", "compote", "chips", "noix", "amande",
        "cacahuete", "olive",
    ],
}


def _normalize(value: str) -> str:
    """Minuscule et sans accents, pour des comparaisons robustes."""
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


def guess_category(name: str) -> str:
    """Devine la categorie d'un aliment a partir de son nom (mots-cles)."""
    normalized_name = _normalize(name)
    for category, keywords in _KEYWORDS.items():
        for keyword in keywords:
            if _normalize(keyword) in normalized_name:
                return category
    return DEFAULT_CATEGORY


def is_valid_category(category: str) -> bool:
    """Verifie qu'une valeur de categorie fait partie de la liste connue."""
    return category in CATEGORIES
