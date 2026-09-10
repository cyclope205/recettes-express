"""Constantes pour l'integration Recettes du Frigo."""

DOMAIN = "recettes_du_frigo"

CONF_GEMINI_API_KEY = "gemini_api_key"

DEFAULT_NAME = "Recettes du Frigo"

# Emplacements de stockage geres
STORAGE_FRIDGE = "frigo"
STORAGE_PANTRY = "garde_manger"

STORAGE_LOCATIONS = [STORAGE_FRIDGE, STORAGE_PANTRY]

# Unites disponibles pour les quantites en stock
UNITS = ["g", "kg", "ml", "l", "piece", "boite", "paquet"]
