"""Constantes pour l'integration Recettes Express."""

DOMAIN = "recettes_express"

CONF_GEMINI_API_KEY = "gemini_api_key"

DEFAULT_NAME = "Recettes Express"

# Unites disponibles pour les quantites en stock
UNITS = ["g", "kg", "cl", "l", "piece", "boite", "paquet"]

# Cle du fichier de stockage persistant (Store helper). Volontairement PAS
# derivee de DOMAIN : ce projet s'appelait "recettes_du_frigo" avant d'etre
# renomme "recettes_express" - garder cette cle stable evite de perdre le
# stock deja enregistre par les utilisateurs lors du renommage.
STORAGE_KEY = "recettes_du_frigo.stock"
STORAGE_VERSION = 1

# Cle du fichier de stockage des dernieres recettes suggerees, pour
# qu'elles survivent a un redemarrage de Home Assistant (accept_recipe
# dependait auparavant d'un etat uniquement en memoire).
SUGGESTIONS_STORAGE_KEY = "recettes_du_frigo.last_suggestions"

# Nombre de jours pour considerer un aliment "bientot perime"
DEFAULT_EXPIRING_SOON_DAYS = 3

# Categories pour le classement automatique des aliments dans la carte
# (voir categorize.py). DEFAULT_CATEGORY est le repli quand aucun mot-cle
# ne correspond.
CATEGORIES = [
    "fruits_legumes",
    "viandes_poissons",
    "produits_laitiers",
    "surgeles",
    "pain_boulangerie",
    "condiments_epices",
    "boissons",
    "epicerie",
    "autres",
]
CATEGORY_LABELS = {
    "fruits_legumes": "Fruits & légumes",
    "viandes_poissons": "Viandes & poissons",
    "produits_laitiers": "Produits laitiers",
    "surgeles": "Surgelés",
    "pain_boulangerie": "Pain & boulangerie",
    "condiments_epices": "Condiments & épices",
    "boissons": "Boissons",
    "epicerie": "Épicerie",
    "autres": "Autres",
}
DEFAULT_CATEGORY = "autres"

# --- Services ---
SERVICE_ADD_ITEM = "add_item"
SERVICE_REMOVE_ITEM = "remove_item"
SERVICE_UPDATE_ITEM = "update_item"
SERVICE_ADD_ITEM_FROM_PHOTO = "add_item_from_photo"
SERVICE_ADD_ITEM_FROM_VOICE = "add_item_from_voice"
SERVICE_SUGGEST_RECIPES = "suggest_recipes"
SERVICE_ACCEPT_RECIPE = "accept_recipe"

# --- Champs de service / attributs ---
ATTR_ITEM_ID = "item_id"
ATTR_ITEM_IDS = "item_ids"
ATTR_NAME = "name"
ATTR_QUANTITY = "quantity"
ATTR_UNIT = "unit"
ATTR_EXPIRATION_DATE = "expiration_date"
ATTR_CATEGORY = "category"
ATTR_IMAGE_PATH = "image_path"
ATTR_IMAGE_BASE64 = "image_base64"
ATTR_AUDIO_BASE64 = "audio_base64"
ATTR_AUDIO_MIME_TYPE = "audio_mime_type"
ATTR_CAMERA_ENTITY_ID = "camera_entity_id"
ATTR_MAX_RECIPES = "max_recipes"
ATTR_RECIPE_INDEX = "recipe_index"

# Donnees en memoire (non persistees) : dernieres recettes suggerees par entree
DATA_LAST_SUGGESTIONS = "last_suggestions"

# Signal dispatcher envoye a chaque changement de stock, pour que les capteurs
# se mettent a jour immediatement au lieu d'attendre le polling (~30s)
SIGNAL_STOCK_UPDATED = f"{DOMAIN}_stock_updated"

# Point de terminaison Gemini (REST)
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
# gemini-3.5-flash-lite : le Flash-Lite le plus recent de la gamme, avec
# un quota gratuit journalier nettement plus genereux et stable que les
# modeles Gemini 3.x "preview" grand format (ex. gemini-3.6-flash, plafonne
# a ~20 requetes/jour en gratuit - c'est ce qui causait les erreurs 429
# "RESOURCE_EXHAUSTED"). Un seul modele pour la photo et les recettes :
# suffisant pour les deux taches et ca simplifie le suivi du quota (un
# seul compteur journalier a surveiller).
GEMINI_VISION_MODEL = "gemini-3.5-flash-lite"
GEMINI_TEXT_MODEL = "gemini-3.5-flash-lite"
