"""Tests for the automatic food categorization (categorize.py)."""
from __future__ import annotations

from custom_components.recettes_express.categorize import guess_category, is_valid_category
from custom_components.recettes_express.const import CATEGORIES, DEFAULT_CATEGORY


# --- guess_category ---------------------------------------------------


def test_guess_category_fruits_legumes():
    assert guess_category("Tomate") == "fruits_legumes"
    assert guess_category("Pommes de terre") == "fruits_legumes"
    assert guess_category("Courgette bio") == "fruits_legumes"


def test_guess_category_viandes_poissons():
    assert guess_category("Blanc de poulet") == "viandes_poissons"
    assert guess_category("Saumon fume") == "viandes_poissons"
    assert guess_category("Oeufs") == "viandes_poissons"


def test_guess_category_produits_laitiers():
    assert guess_category("Yaourt nature") == "produits_laitiers"
    assert guess_category("Fromage rape") == "produits_laitiers"
    assert guess_category("Lait demi-ecreme") == "produits_laitiers"


def test_guess_category_boissons():
    assert guess_category("Jus d'orange") == "boissons"
    assert guess_category("Eau petillante") == "boissons"


def test_guess_category_epicerie():
    assert guess_category("Riz basmati") == "epicerie"
    assert guess_category("Farine de ble") == "epicerie"
    assert guess_category("Chocolat noir") == "epicerie"


def test_guess_category_unknown_falls_back_to_default():
    assert guess_category("Xyzzy inconnu 42") == DEFAULT_CATEGORY
    assert guess_category("") == DEFAULT_CATEGORY


def test_guess_category_is_case_and_accent_insensitive():
    assert guess_category("FROMAGE") == "produits_laitiers"
    assert guess_category("frômage") == "produits_laitiers"
    assert guess_category("Crème fraîche") == "produits_laitiers"


def test_guess_category_lait_is_dairy_not_beverage():
    # "lait" matches both produits_laitiers and boissons keyword lists in
    # spirit, but produits_laitiers must win (checked first) - milk reads
    # as dairy to a French user, not as a generic drink.
    assert guess_category("Lait entier") == "produits_laitiers"


def test_guess_category_matches_substring_within_longer_name():
    assert guess_category("Steak hache de boeuf") == "viandes_poissons"


# --- is_valid_category ---------------------------------------------------


def test_is_valid_category_accepts_known_categories():
    for category in CATEGORIES:
        assert is_valid_category(category) is True


def test_is_valid_category_rejects_unknown_value():
    assert is_valid_category("inconnu") is False
    assert is_valid_category("") is False
