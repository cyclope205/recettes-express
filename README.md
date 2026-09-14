# Recettes Express

[![Release](https://img.shields.io/github/v/release/cyclope205/recettes-express)](https://github.com/cyclope205/recettes-express/releases)
[![Build](https://img.shields.io/github/actions/workflow/status/cyclope205/recettes-express/validate.yml?branch=main)](https://github.com/cyclope205/recettes-express/actions/workflows/validate.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-cyclope205-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/cyclope205)
[![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/cyclope205)

Integration Home Assistant pour gerer le stock d'aliments (frigo, garde-manger) et obtenir des suggestions de recettes anti-gaspi generees par IA (Gemini), avec deduction automatique du stock.

## Fonctionnalites

- Ajout d'aliments par photo (reconnaissance IA) ou manuellement, avec date de peremption obligatoire
- Gestion du stock : modification, suppression, recherche, tri (nom ou date de peremption)
- Suggestions de recettes anti-gaspi a partir du stock (ou d'une selection d'aliments), avec temps de preparation estime
- Validation d'une recette : deduction automatique des ingredients utilises, la recette reste affichee jusqu'a confirmation de fin
- Carte Lovelace personnalisee incluse (stock, aliments bientot perimes, recettes suggerees)
- Capteurs : nombre d'aliments en stock, aliments bientot perimes

## Installation

### Via HACS (recommande)

1. HACS > menu (...) > Depots personnalises
2. Ajouter `cyclope205/recettes-express` en categorie Integration

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=cyclope205&repository=recettes-express&category=integration)

3. Installer "Recettes Express" depuis HACS
4. Redemarrer Home Assistant

### Manuelle

Copier le dossier `custom_components/recettes_express` dans le dossier `custom_components` de votre configuration Home Assistant, puis redemarrer.

## Configuration

L'integration se configure via l'interface (Parametres > Appareils et services > Ajouter une integration > Recettes Express). Elle necessite une cle API Gemini pour la reconnaissance photo et les suggestions de recettes.

La carte Lovelace est enregistree automatiquement. Exemple de configuration :

```yaml
type: custom:recettes-express-card
entity_stock: sensor.aliments
entity_expiring: sensor.bientot_perime
```

## Services

- `recettes_express.add_item` : ajouter un aliment au stock
- `recettes_express.update_item` : modifier un aliment existant
- `recettes_express.remove_item` : retirer un aliment du stock
- `recettes_express.add_item_from_photo` : detecter des aliments a partir d'une photo
- `recettes_express.suggest_recipes` : demander des suggestions de recettes
- `recettes_express.accept_recipe` : valider une recette et deduire les ingredients du stock

## Licence

MIT — voir [LICENSE](LICENSE).

<div align="center">

-------------------------------------------------------------------------------------------------------------------------------------------------------------------
### ☕ Cette integration te plait ?

Si elle te fait gagner du temps, un petit don est toujours apprecie : ca m'aide a maintenir le projet et a ajouter de nouvelles fonctionnalites.

<a href="https://buymeacoffee.com/cyclope205"><img src="https://img.shields.io/badge/Buy%20Me%20A%20Coffee-cyclope205-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black" alt="Buy Me A Coffee"></a>
<a href="https://paypal.me/cyclope205"><img src="https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white" alt="PayPal"></a>

</div>
