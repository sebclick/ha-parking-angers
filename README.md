# Parking Angers

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Validate](https://github.com/sebclick/ha-parking-angers/actions/workflows/validate.yml/badge.svg)](https://github.com/sebclick/ha-parking-angers/actions/workflows/validate.yml)
[![Tests](https://github.com/sebclick/ha-parking-angers/actions/workflows/tests.yml/badge.svg)](https://github.com/sebclick/ha-parking-angers/actions/workflows/tests.yml)

Intégration [Home Assistant](https://www.home-assistant.io/) qui affiche le **nombre de places libres**
et le **taux d'occupation** des parkings d'Angers gérés par ALTER, à partir de l'open data de
[data.angers.fr](https://data.angers.fr/explore/dataset/parking-angers/).

## Fonctionnalités

- Un appareil par parking sélectionné, avec :
  - **Places libres** (`sensor`) : la valeur principale. Ses attributs donnent la position GPS
    (le parking apparaît sur la carte HA), l'adresse, la hauteur maximale, le nombre de places PMR
    et de bornes de recharge, et les tarifs 1 h / 2 h / 3 h / 4 h / 24 h ;
  - **Taux d'occupation** (`sensor`, en %) ;
  - **Capacité** (`sensor`, diagnostic) ;
  - **Complet** (`binary_sensor`) : allumé quand le taux d'occupation atteint le seuil choisi (95 % par défaut).
- Un appareil « Open data Angers » avec le capteur de diagnostic **Données figées**, qui s'allume
  quand aucune valeur n'a bougé depuis 3 heures. Un signalement apparaît alors aussi dans
  **Paramètres → Système → Réparations**. Il disparaît tout seul dès que les valeurs bougent à nouveau.
- Intervalle de rafraîchissement réglable de 1 à 60 minutes (10 par défaut).
- Données de référence (capacité, adresse, tarifs…) embarquées, puis mises à jour une fois par jour
  depuis le jeu `angers_stationnement`.
- Interface en français et en anglais, diagnostics téléchargeables.

## Installation

### Via HACS (recommandé)

1. Dans HACS, menu ⋮ → **Dépôts personnalisés**, ajoutez `https://github.com/sebclick/ha-parking-angers`
   avec la catégorie **Intégration**.
2. Cherchez « Parking Angers » et installez-la.
3. Redémarrez Home Assistant.

### Manuelle

Copiez le dossier `custom_components/parking_angers` dans le dossier `custom_components`
de votre configuration Home Assistant, puis redémarrez.

## Configuration

**Paramètres → Appareils et services → Ajouter une intégration → Parking Angers.**

| Option | Description | Défaut |
|---|---|---|
| Parkings | Parkings à suivre (un appareil par parking) | tous |
| Intervalle de mise à jour | En minutes, de 1 à 60 | 10 |
| Seuil « complet » | Taux d'occupation à partir duquel le parking est complet, de 50 à 100 % | 95 % |

Tout se modifie ensuite via le bouton **Configurer** de l'intégration. Les appareils des parkings
décochés sont supprimés.

Les entités sont nommées d'après le parking, par exemple `sensor.parking_du_ralliement_places_libres`,
`sensor.parking_du_ralliement_taux_d_occupation` et `binary_sensor.parking_du_ralliement_complet`.

## Exemple de carte Lovelace

```yaml
type: entities
title: Parkings du centre
state_color: true
entities:
  - entity: sensor.parking_du_ralliement_places_libres
    secondary_info: last-changed
  - entity: sensor.parking_fleur_d_eau_les_halles_places_libres
  - entity: sensor.parking_du_mail_places_libres
  - type: divider
  - entity: binary_sensor.open_data_angers_donnees_figees
```

Avec des jauges :

```yaml
type: grid
columns: 3
cards:
  - type: gauge
    entity: sensor.parking_du_ralliement_taux_d_occupation
    name: Ralliement
    severity: { green: 0, yellow: 80, red: 95 }
  - type: gauge
    entity: sensor.parking_du_mail_taux_d_occupation
    name: Mail
    severity: { green: 0, yellow: 80, red: 95 }
  - type: gauge
    entity: sensor.parking_moliere_taux_d_occupation
    name: Molière
    severity: { green: 0, yellow: 80, red: 95 }
```

Et une carte des parkings :

```yaml
type: map
entities:
  - sensor.parking_du_ralliement_places_libres
  - sensor.parking_du_mail_places_libres
  - sensor.parking_du_chateau_places_libres
```

> Vérifiez les identifiants exacts de vos entités dans **Paramètres → Entités** : ils dépendent
> de la langue du système au moment de l'installation.

## Bon à savoir

- **La source n'est pas vraiment temps réel**, et il arrive que le flux de data.angers.fr reste figé
  pendant des heures. Le capteur « Données figées » et le signalement Réparations sont là pour ça :
  les autres capteurs restent disponibles avec la dernière valeur connue, à vous de juger.
- **Correspondance des parkings** : le flux temps réel utilise des noms techniques (`Republique`,
  `Berges De Maine`…) qui ne correspondent pas aux identifiants du jeu de référence. La table de
  correspondance a été reconstituée à la main. Deux associations restent à confirmer :
  `Mitterrand Rennes` ↔ Parking Saint-Serge Mitterrand et `Berges De Maine` ↔ Parking Saint-Serge Cinéma.
- **Parking du Château** : absent du jeu de référence, ses données (300 places, position approximative)
  sont saisies à la main ; ses tarifs ne sont pas connus.
- **Nouveau parking côté source** : il apparaît dans la liste de configuration avec son nom technique
  et seulement le nombre de places libres (sans capacité, ni taux d'occupation, ni « Complet »).
  Si un parking est renommé côté source, de nouvelles entités sont créées.
- **Quota** : l'API anonyme autorise 5 000 requêtes par jour et par adresse IP. En cas de dépassement,
  l'intégration attend la remise à zéro du quota (minuit UTC).
- Les attributs statiques (position, tarifs…) ne sont pas enregistrés dans l'historique.

## Dépannage

Pour activer les journaux détaillés :

```yaml
logger:
  logs:
    custom_components.parking_angers: debug
```

Les diagnostics (menu ⋮ de l'intégration → **Télécharger les diagnostics**) contiennent la dernière
réponse brute de l'API, l'état de la détection des données figées et la liste des parkings inconnus.

## Développement

```bash
uv venv --python 3.14 && source .venv/bin/activate
uv pip install -r requirements_test.txt ruff syrupy pytest-cov
pytest --cov=custom_components.parking_angers --cov-report=term-missing
ruff check . && ruff format --check .
```

Un Home Assistant de test se lance avec `docker compose up` (configuration dans `.ha-config/`,
`custom_components/` monté).

Quand le jeu de référence change, mettez à jour `tests/fixtures/reference.json` puis régénérez
les données embarquées :

```bash
python scripts/build_parkings_json.py
```

La table de correspondance et les données saisies à la main sont dans ce script.

## Licence

Code sous licence [MIT](LICENSE).

Données : **ALTER / data.angers.fr**, sous licence
[Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/1-0/).

Icône (`custom_components/parking_angers/brand/`) : dessin dérivé de la photo
[« Angers 2012 3 »](https://commons.wikimedia.org/wiki/File:Angers_2012_3.jpg) de Smiley.toerist
(Wikimedia Commons), sous licence [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
L'icône est elle-même diffusée sous CC BY-SA 4.0.
