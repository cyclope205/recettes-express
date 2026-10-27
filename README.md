# Recettes Express

[![HACS: Default](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)
[![Release](https://img.shields.io/github/v/release/cyclope205/recettes-express)](https://github.com/cyclope205/recettes-express/releases)
[![Build](https://github.com/cyclope205/recettes-express/actions/workflows/validate.yml/badge.svg)](https://github.com/cyclope205/recettes-express/actions/workflows/validate.yml)
[![Tests](https://github.com/cyclope205/recettes-express/actions/workflows/tests.yml/badge.svg)](https://github.com/cyclope205/recettes-express/actions/workflows/tests.yml)
[![Issues](https://img.shields.io/github/issues/cyclope205/recettes-express)](https://github.com/cyclope205/recettes-express/issues)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/cyclope205/recettes-express/blob/main/LICENSE)
[![Downloads](https://img.shields.io/github/downloads/cyclope205/recettes-express/total)](https://github.com/cyclope205/recettes-express/releases)
[![Downloads latest](https://img.shields.io/github/downloads/cyclope205/recettes-express/latest/total)](https://github.com/cyclope205/recettes-express/releases/latest)
[![Stars](https://img.shields.io/github/stars/cyclope205/recettes-express)](https://github.com/cyclope205/recettes-express/stargazers)
[![Forks](https://img.shields.io/github/forks/cyclope205/recettes-express)](https://github.com/cyclope205/recettes-express/network/members)

---

### ❤️ Sponsors GitHub

<!--START_SECTION:github-sponsors-->
<!-- Aucun sponsor GitHub public actif pour le moment -->
<!--END_SECTION:github-sponsors-->

---
### ☕ Merci aux donateurs

<!--START_SECTION:buy-me-a-coffee-->
<!-- Les nouveaux dons seront ajoutés ici automatiquement -->
<!--END_SECTION:buy-me-a-coffee-->

---

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-cyclope205-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://bmc-eight-red.vercel.app/api/donate?repo=recettes-express) [![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://bmc-eight-red.vercel.app/api/paypal?repo=recettes-express&amount=5)
<img src="https://raw.githubusercontent.com/cyclope205/recettes-express/main/custom_components/recettes_express/brand/icon.png" alt="Recettes Express" width="32">

### ☕ Offrez-moi un café pour m'aider à rester éveillé et coder vos intégrations préférées !

En remerciement, votre nom apparaîtra (de façon anonymisée) dans la section « ☕ Merci aux donateurs » ci-dessus.

---

Intégration Home Assistant pour gérer le stock d'aliments (frigo, garde-manger) et obtenir des suggestions de recettes anti-gaspi générées par IA (Gemini), avec déduction automatique du stock.


## Captures d'écran

---


Vue d'ensemble : bloc d'actions (photo, ajout manuel) et recettes suggérées juste sous l'entête, aliments à suivre en dessous :

<img width="460" alt="Recettes Express - accueil" src="https://raw.githubusercontent.com/cyclope205/recettes-express/main/screenshots/84f87155-FullSizeRender.jpeg" />

---
Suggestions de recettes générées par IA, affichées directement sous le bloc d'actions :

<img width="415" alt="Recettes Express - suggestion de recette" src="https://raw.githubusercontent.com/cyclope205/recettes-express/main/screenshots/51bc5666-IMG_8191.png" />

## Fonctionnalités

- Ajout d'aliments par photo, par micro (reconnaissance vocale en français) ou manuellement, avec date de péremption obligatoire
- Gestion du stock : modification, suppression, recherche, tri (nom ou date de péremption)
- Suggestions de recettes anti-gaspi à partir du stock (ou d'une sélection d'aliments), avec temps de préparation estimé, et options facultatives via le bouton ⚙️ (nombre de personnes, végétarien uniquement, temps de préparation maximum)
- Validation d'une recette : déduction automatique des ingrédients utilisés, la recette reste affichée jusqu'à confirmation de fin
- Catégorisation automatique des aliments par mots-clés (fruits & légumes, viandes & poissons, produits laitiers, surgelés, pain & boulangerie, condiments & épices, boissons, épicerie, autres)
- Section "Aliments sélectionnés" épinglée en haut de la liste, qui apparaît dès qu'un aliment est coché
- Carte Lovelace personnalisée incluse (stock, aliments bientôt périmés, recettes suggérées), avec le bloc d'actions et les recettes juste sous l'entête pour un accès rapide
- Capteurs : nombre d'aliments en stock, aliments bientôt périmés

## Bien photographier un aliment

Pour que la reconnaissance par IA renseigne seule le nom de l'aliment et sa date de péremption (DLC), la photo doit montrer **à la fois** :

- le nom / descriptif du produit (étiquette de l'emballage)
- la date de péremption ou "à consommer jusqu'au" (DLC), imprimée ou estampillée sur l'emballage

Quelques conseils pour une détection fiable :

- à plat, cadrez l'emballage en entier, sans reflet ni ombre sur le texte
- rapprochez l'appareil ou zoomez pour que la date de péremption soit nette et lisible
- si le nom du produit et la DLC ne sont pas du même côté de l'emballage, prenez une photo qui montre les deux, ou repliez l'emballage pour les faire apparaître ensemble

Exemples de photos correctement cadrées (nom du produit et DLC lisibles) :

<img width="300" alt="Exemple de photo : nom du produit et DLC visibles (jambon)" src="https://raw.githubusercontent.com/cyclope205/recettes-express/main/screenshots/33474e6e-photo.jpeg" />
<img width="300" alt="Exemple de photo : nom du produit et DLC visibles (saucisse de Morteau)" src="https://raw.githubusercontent.com/cyclope205/recettes-express/main/screenshots/bb5cc721-photo.jpeg" />

Sans ces informations visibles sur la photo, l'IA peut se tromper sur le nom de l'aliment ou ne pas détecter de date, ce qui oblige à compléter les champs manquants à la main.

Si la date de péremption n'est pas lisible sur la photo, l'IA peut aussi l'estimer à partir du type de produit plutôt que de la lire telle quelle. Dans ce cas, l'aliment ajouté au stock précise si la date vient de l'emballage ("imprimée") ou d'une estimation de l'IA ("estimée"), pour savoir quand la vérifier vous-même.

## Personnaliser les suggestions de recettes

À côté du bouton "👨‍🍳 Suggérer des recettes", un bouton ⚙️ ouvre un petit panneau d'options facultatives, prises en compte par l'IA au moment de générer les recettes :

- **👥 Personnes** : adapte les quantités des recettes pour ce nombre de convives.
- **⏱️ Temps max (min)** : écarte les recettes dont le temps de préparation total dépasserait cette limite.
- **🥦 Végétarien uniquement** : ne propose que des recettes sans viande ni poisson.

Ces champs sont optionnels : laissés vides ou décochés, le comportement est identique à avant (aucune contrainte supplémentaire). Comme pour le reste des suggestions, il s'agit de consignes données à l'IA et non de garanties absolues — vérifiez toujours la recette proposée. Un garde-fou vérifie chaque recette suggérée avant affichage : toute recette qui mentionnerait un ingrédient absent du stock (hors basiques courants comme sel, huile ou eau) est automatiquement écartée.

<img width="380" alt="Recettes Express - options de suggestion de recettes (personnes, végétarien, temps max)" src="https://github.com/user-attachments/assets/1c06f812-b905-4a3e-8b87-ff22f950d43a" />

## Ajouter des aliments par micro

En plus de la photo, un bouton "🎤 Ajouter par micro" permet d'enregistrer un court message vocal (en français) pour ajouter des aliments sans les taper. Énoncez simplement ce que vous rangez, par exemple : *"deux yaourts nature, ils périment dans une semaine"* ou *"une boîte de conserve de haricots verts"*.

Comme pour la photo, l'IA (Gemini) analyse l'enregistrement et propose les aliments détectés pour confirmation avant tout ajout au stock. Si vous ne précisez pas de quantité, d'unité ou de date de péremption, des valeurs par défaut raisonnables sont proposées et restent modifiables avant validation.

> ⚠️ **Le micro nécessite un accès à Home Assistant en HTTPS** (certificat local, reverse proxy, Nabu Casa, certificats Tailscale...). C'est une restriction des navigateurs eux-mêmes (l'API `getUserMedia` est bloquée hors HTTPS/localhost) : c'est exactement la même limitation que rencontre l'Assist officiel de Home Assistant en HTTP simple. Sur un accès en `http://` (IP locale, Tailscale sans certificat...), le bouton affichera un message expliquant qu'il faut passer en HTTPS. L'ajout par photo n'est pas concerné, il fonctionne quel que soit l'accès.

## Installation

### Via HACS (recommandé)

## Installation

1. Ouvrir Recettes Express dans HACS et l'installer :

   [![Ouvrir HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=cyclope205&repository=recettes-express&category=integration)
   [![Ouvrir dans Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=cyclope205&repository=recettes-express&category=integration)

   ou rechercher **Recettes Express** dans HACS.
3. Télécharger la dernière version de Recettes Express.
4. Redémarrer Home Assistant.
5. Ajouter l'intégration :

   [![Ajouter l'intégration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=recettes_express)

   ou **Paramètres > Appareils et services > Ajouter une intégration > Recettes Express**.
### Manuelle

Copier le dossier `custom_components/recettes_express` dans le dossier `custom_components` de votre configuration Home Assistant, puis redémarrer.

## Ajouter la carte au tableau de bord

Une fois l'intégration installée, la carte doit être ajoutée manuellement à votre tableau de bord :

1. Ouvrez le tableau de bord concerné et cliquez sur le crayon en haut à droite pour passer en mode édition.
2. Cliquez sur "+ Ajouter une carte" en bas de l'écran.
3. Dans la barre de recherche, tapez "Recettes Express" : la carte apparaît dans la liste, cliquez dessus puis sur "Enregistrer".

Alternative en YAML (onglet "Modifier en YAML" de la fenêtre d'ajout de carte) :

```yaml
type: custom:recettes-express-card
```

## Configuration

L'intégration se configure via l'interface (Paramètres > Appareils et services > Ajouter une intégration > Recettes Express). Elle nécessite une clé API Gemini pour la reconnaissance photo et les suggestions de recettes.

La carte Lovelace est enregistrée automatiquement. Exemple de configuration :

```yaml
type: custom:recettes-express-card
entity_stock: sensor.aliments
entity_expiring: sensor.bientot_perime
```

## Services

- `recettes_express.add_item` : ajouter un aliment au stock
- `recettes_express.update_item` : modifier un aliment existant
- `recettes_express.remove_item` : retirer un aliment du stock
- `recettes_express.add_item_from_photo` : détecter des aliments à partir d'une photo
- `recettes_express.add_item_from_voice` : détecter des aliments à partir d'un enregistrement vocal
- `recettes_express.suggest_recipes` : demander des suggestions de recettes (options facultatives : `servings`, `vegetarian`, `max_prep_minutes`)
- `recettes_express.accept_recipe` : valider une recette et déduire les ingrédients du stock

## Licence

MIT — voir [LICENSE](https://github.com/cyclope205/recettes-express/blob/main/LICENSE).
