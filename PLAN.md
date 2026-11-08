# Parking Angers – Intégration Home Assistant : plan de développement

> Objectif : afficher dans Home Assistant le nombre de places libres et le taux d'occupation
> des parkings d'Angers gérés par ALTER, à partir de l'open data de data.angers.fr.

Statut : **prêt à démarrer** · Rédigé le 2026-11-08

---

## 1. Décisions validées

| Sujet | Décision |
|---|---|
| Type | Intégration personnalisée (`custom_components/parking_angers`), distribuée via HACS |
| Domaine HA | `parking_angers` |
| Rafraîchissement | Configurable de **1 à 60 min**, **10 min par défaut** (la source n'est pas vraiment temps réel) |
| Données de référence | **Hybride** : mapping + données de secours embarqués, enrichis par l'API `angers_stationnement` (relue toutes les 24 h) |
| Seuil « complet » | En **% d'occupation**, configurable (défaut **95 %**) |
| `binary_sensor` « Complet » | Oui |
| Capteur global (total ville) | **Non** |
| Capacité du parking Château | **300 places**, saisie à la main (absent du jeu de référence) |
| Contact data.angers.fr / ALTER sur le flux figé | Fait par le porteur du projet, hors dev |

---

## 2. Sources de données

Plateforme **Opendatasoft**, API Explore v2.1, sans authentification.

### 2.1 Temps réel : `parking-angers`

```
GET https://data.angers.fr/api/explore/v2.1/catalog/datasets/parking-angers/records?limit=100
```

```json
{"total_count": 19, "results": [{"disponible": 13, "nom": "Republique"}, ...]}
```

| Champ | Type | Remarque |
|---|---|---|
| `nom` | text | Identifiant technique (≠ nom grand public). **Clé de l'intégration.** |
| `disponible` | int | Places libres |
| `record_timestamp` | datetime | Seulement avec `select=…,record_timestamp`. **Inexploitable** : retard d'1 h (bug de fuseau horaire), et il avance chaque minute même quand les valeurs sont figées. **On ne l'utilise pas.** |

### 2.2 Référence : `angers_stationnement` (18 enregistrements, mis à jour une fois par an)

```
GET https://data.angers.fr/api/explore/v2.1/catalog/datasets/angers_stationnement/records?limit=100
```

Champs utilisés : `id`, `nom`, `adresse`, `url`, `nb_places`, `nb_pmr`, `nb_voitures_electriques`,
`hauteur_max` (texte, en cm), `xlong`/`ylat` (texte → float), `gratuit` (`"VRAI"`/`"FAUX"` → bool),
`type_ouvrage`, `tarif_1h`, `tarif_2h`, `tarif_3h`, `tarif_4h`, `tarif_24h`.

Qualité des données : beaucoup de `null` et quelques valeurs douteuses (ex. `tarif_24h = 0.6` pour le Mail).
On les expose telles quelles, sans corriger.

### 2.3 Contraintes de l'API

- Quota anonyme : **5 000 requêtes/jour/IP**, remis à zéro à 00:00 UTC. En-têtes `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
  Au pire (1 min), on fait 1 440 appels/jour plus 1 appel de référence : ça passe.
- `Cache-Control: no-cache`, pas d'ETag ni de Last-Modified, donc pas de requête conditionnelle.
- Erreurs au format JSON `{"error_code": "...", "message": "..."}`. Exemples dans `tests/fixtures/error_404.json` et `error_400.json`.
- Le dataset temps réel affiche « momentanément indisponible ». **Constat du 07 au 08/11/2026 : les 19 valeurs n'ont pas bougé pendant plus de 16 h**, d'où la détection des données figées (§ 5.4).

### 2.4 Exemples de réponses (déjà capturés)

| Fichier | Contenu |
|---|---|
| `tests/fixtures/realtime.json` | Réponse réelle du temps réel (19 parkings) |
| `tests/fixtures/reference.json` | Réponse réelle de la référence (18 parkings) |
| `tests/fixtures/error_404.json` | Dataset inexistant |
| `tests/fixtures/error_400.json` | Requête ODSQL invalide |

---

## 3. Mapping temps réel → référence

La jointure indiquée dans la doc (`id_parking = nom`) **ne fonctionne pas** : `id` vaut `49007-P-xxx`.
Ce mapping a été reconstitué en comparant les capacités et les URL.

| `nom` temps réel | `id` référence | Nom grand public | Places | Confiance |
|---|---|---|---|---|
| Berges De Maine | 49007-P-001 | Parking Saint-Serge Cinéma | 305 | moyenne (son URL contient « berges-du-maine ») |
| Mitterrand Rennes | 49007-P-002 | Parking Saint-Serge Mitterrand | 133 | **à confirmer** (par élimination) |
| Republique | 49007-P-003 | Parking Fleur d'Eau Les Halles | 383 | bonne |
| Confluences | 49007-P-004 | Parking Confluences | 30 | bonne |
| Saint Laud 2 | 49007-P-005 | Parking St Laud II | 576 | bonne |
| Ralliement | 49007-P-006 | Parking du Ralliement | 432 | bonne |
| Mitterrand Maine | 49007-P-007 | Parking Saint-Serge Mitterrand Maine | 151 | bonne |
| Larrey | 49007-P-008 | Parking Larrey | 28 | bonne |
| Bressigny | 49007-P-009 | Parking Bressigny | 172 | bonne |
| Mail | 49007-P-010 | Parking du Mail | 960 | bonne |
| Saint Laud | 49007-P-011 | Parking St Laud | 450 | bonne |
| Haras Public | 49007-P-012 | Parking Haras Public | 112 | bonne |
| Saint Serge Patinoire | 49007-P-013 | Parking Saint-Serge Patinoire | 234 | bonne |
| Moliere | 49007-P-014 | Parking Molière | 416 | bonne |
| Leclerc | 49007-P-015 | Parking Leclerc | 235 | bonne |
| Marengo | 49007-P-016 | Parking Marengo | 305 | bonne |
| Quai | 49007-P-017 | Parking Le Quai | 180 | bonne |
| Maternite | 49007-P-018 | Parking Maternité | 56 | bonne |
| **Chateau** | *(aucun)* | Parking du Château | **300** | saisie à la main |

Données de secours pour **Chateau**, tirées de https://parking-angers.fr/parking/parking-chateau/ :
300 places, 6 PMR, hauteur max 1,90 m, adresse « Rue de Quatrebarbes, 49100 Angers », accès 24h/24.
Coordonnées **approximatives** (géocodage de la rue via api-adresse.data.gouv.fr) : lat `47.46892`, lon `-0.561197`.
`gratuit: false`. Les tarifs ne sont pas connus de façon fiable (`null`).

> À demander à ALTER dans le mail : confirmer `Mitterrand Rennes ↔ P-002` et `Berges De Maine ↔ P-001`,
> et l'ajout du Château dans `angers_stationnement`.

### 3.1 Le fichier `parkings.json` embarqué (source unique)

`custom_components/parking_angers/data/parkings.json`, indexé par le `nom` temps réel :

```json
{
  "Ralliement": {
    "ref_id": "49007-P-006",
    "name": "Parking du Ralliement",
    "capacity": 432,
    "address": "5 Place du Ralliement, 49000 Angers",
    "latitude": 47.4712242886,
    "longitude": -0.5518064832,
    "url": "http://parking-angers.fr/parking-du-ralliement-2/",
    "max_height_m": 1.9,
    "structure_type": "ouvrage",
    "free": false,
    "pmr_spaces": 9,
    "ev_chargers": 3,
    "rates": {"1h": 0.0, "2h": 2.0, "3h": 4.0, "4h": 6.0, "24h": 20.0}
  },
  "Chateau": {
    "ref_id": null,
    "name": "Parking du Château",
    "capacity": 300,
    "...": "..."
  }
}
```

Ce fichier est **généré** par `scripts/build_parkings_json.py`, qui prend en entrée `tests/fixtures/reference.json`
plus une table de surcharges manuelles (mapping et Château). On le relance quand la référence change.

### 3.2 Règle de fusion (à l'exécution)

Pour chaque `nom` reçu en temps réel :

```
static = parkings.json[nom]                                  # peut être absent
api    = reference_api[static.ref_id] si ref_id et dispo
final  = static, écrasé champ par champ par les valeurs NON nulles de api
```

- Le nom affiché vient de `final.name`, sinon du `nom` brut.
- **Un `nom` inconnu** (nouveau parking côté source) est proposé dans la liste de configuration
  avec seulement les places libres. Taux d'occupation et « Complet » sont indisponibles faute de capacité. On écrit une fois un log `info`.
- **Si la référence API échoue**, on garde `parkings.json` seul et on écrit un log `warning`, sans erreur visible.

---

## 4. Arborescence cible

```
ha-parking-angers/
├── PLAN.md
├── README.md                     # installation HACS/manuelle, captures, attribution ODbL
├── LICENSE                       # MIT (code) – données sous ODbL
├── hacs.json
├── pyproject.toml                # ruff, pytest, deps de dev
├── requirements_test.txt         # pytest-homeassistant-custom-component (version alignée sur la version HA ciblée)
├── .github/workflows/
│   ├── validate.yml              # hassfest + HACS action
│   └── tests.yml                 # ruff + pytest
├── scripts/
│   └── build_parkings_json.py
├── docker-compose.yml            # HA de dev avec custom_components monté
├── custom_components/parking_angers/
│   ├── __init__.py               # setup/unload entry, runtime_data, listener d'options
│   ├── manifest.json
│   ├── const.py                  # DOMAIN, URLs, défauts, bornes
│   ├── api.py                    # client HTTP sans dépendance HA (testable isolément)
│   ├── models.py                 # dataclasses ParkingStatic, ParkingState, ParkingData
│   ├── coordinator.py            # DataUpdateCoordinator + fusion + détection figée
│   ├── entity.py                 # ParkingEntity (CoordinatorEntity, DeviceInfo)
│   ├── sensor.py
│   ├── binary_sensor.py
│   ├── config_flow.py            # ConfigFlow + OptionsFlow
│   ├── diagnostics.py
│   ├── repairs.py                # (optionnel : ticket non réparable → simple ir.async_create_issue)
│   ├── icons.json
│   ├── strings.json
│   ├── translations/fr.json
│   ├── translations/en.json
│   └── data/parkings.json
└── tests/
    ├── conftest.py
    ├── fixtures/…                # déjà présents
    ├── test_api.py
    ├── test_coordinator.py
    ├── test_config_flow.py
    ├── test_sensor.py
    ├── test_binary_sensor.py
    └── test_diagnostics.py
```

### `manifest.json`

```json
{
  "domain": "parking_angers",
  "name": "Parking Angers",
  "codeowners": ["@<github-user>"],
  "config_flow": true,
  "documentation": "https://github.com/<github-user>/ha-parking-angers",
  "integration_type": "service",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/<github-user>/ha-parking-angers/issues",
  "requirements": [],
  "single_config_entry": true,
  "version": "0.1.0"
}
```

### `hacs.json`

```json
{ "name": "Parking Angers", "homeassistant": "2026.1.0", "render_readme": true, "country": "FR" }
```

La version minimale de HA est à caler sur celle utilisée en dev.

---

## 5. Spécifications fonctionnelles

### 5.1 Client API (`api.py`)

```python
class ParkingAngersApi:
    def __init__(self, session: aiohttp.ClientSession) -> None: ...
    async def async_get_availability(self) -> dict[str, int]: ...          # nom -> disponible
    async def async_get_reference(self) -> dict[str, dict[str, Any]]: ...   # id -> champs bruts

class ParkingAngersError(Exception): ...
class ParkingAngersConnectionError(ParkingAngersError): ...   # timeout, DNS, 5xx
class ParkingAngersRateLimitError(ParkingAngersError):        # 429
    retry_after: datetime | None                              # depuis X-RateLimit-Reset
class ParkingAngersResponseError(ParkingAngersError): ...     # 4xx, JSON invalide, schéma inattendu
```

- Timeout 15 s, `User-Agent: HomeAssistant-ParkingAngers/<version>`.
- Session : `async_get_clientsession(hass)`.
- Robuste aux entrées sales : on ignore une entrée sans `nom` ou dont `disponible` n'est pas un entier, et on loggue en `debug`.
- Pas de pagination à gérer (`limit=100` alors qu'il y a 19 parkings). Si `total_count > 100`, on loggue un `warning`.

### 5.2 Modèle (`models.py`)

```python
@dataclass(frozen=True)
class ParkingStatic:
    key: str                 # nom temps réel
    ref_id: str | None
    name: str
    capacity: int | None
    address: str | None
    latitude: float | None
    longitude: float | None
    url: str | None
    max_height_m: float | None
    structure_type: str | None
    free: bool | None
    pmr_spaces: int | None
    ev_chargers: int | None
    rates: dict[str, float | None]

@dataclass(frozen=True)
class ParkingState:
    static: ParkingStatic
    available: int

    @property
    def occupancy(self) -> float | None:   # 0..100, borné ; None si capacité inconnue ou 0
        ...

@dataclass
class ParkingData:
    parkings: dict[str, ParkingState]
    stale: bool
    last_change: datetime | None           # dernier instant où AU MOINS une valeur a changé
```

Calcul : `occupancy = clamp(0, 100, (1 - available / capacity) * 100)`.
Si `available > capacity`, l'occupation vaut 0 (bornage) et on loggue une fois en `debug`.

### 5.3 Coordinateur (`coordinator.py`)

- `DataUpdateCoordinator[ParkingData]`, `update_interval = timedelta(minutes=options["scan_interval"])`.
- `config_entry` passé au constructeur. Le premier rafraîchissement se fait via `async_config_entry_first_refresh()` : en cas d'échec, on lève `ConfigEntryNotReady` et HA réessaie tout seul.
- **Référence** : chargée au premier rafraîchissement, puis rechargée si plus de 24 h se sont écoulées, dans le même cycle. Un échec de la référence n'est jamais bloquant.
- **Gestion d'erreurs** :
  - `ConnectionError` / `ResponseError` → `UpdateFailed` (toutes les entités passent en indisponible).
  - `RateLimitError` → `UpdateFailed(retry_after=…)` : le prochain essai est repoussé à la remise à zéro du quota.
  - Parking sélectionné absent de la réponse → seule son entité est indisponible (`available` dans l'entité).
- Les données de tous les parkings sont gardées, même non sélectionnés : le calcul « figé » en a besoin, et le coût est nul.

### 5.4 Détection des données figées

- On compare l'ensemble `{nom: disponible}` avec le précédent. **Si au moins une valeur change**, `last_change = now`.
- `stale = now - last_change >= STALE_AFTER`, avec **`STALE_AFTER = 3 h`** en constante, non configurable.
  Au démarrage, `last_change = now` : il faut donc 3 h d'observation avant de signaler quoi que ce soit.
  (Choix assumé : pas de persistance entre redémarrages en v1.)
- Passage à `stale = True` :
  - `ir.async_create_issue(hass, DOMAIN, "stale_data", is_fixable=False, severity=WARNING, translation_key="stale_data")`
  - le `binary_sensor` diagnostic « Données figées » passe à `on`.
- Retour à `stale = False` : `ir.async_delete_issue(...)`.
- **Les entités restent disponibles** avec la dernière valeur. C'est à l'utilisateur de juger.

### 5.5 Entités

Toutes utilisent `has_entity_name = True` et un `translation_key`.

**Appareil « parking »**, un par parking sélectionné :
- `identifiers={(DOMAIN, key)}`, `name=static.name`, `manufacturer="ALTER"`, `model=structure_type`,
  `configuration_url=static.url`, `entry_type=DeviceEntryType.SERVICE`.

| translation_key | Plateforme | Unique ID | Détails |
|---|---|---|---|
| `available_spaces` | sensor | `{slug}_available_spaces` | `state_class=MEASUREMENT`, unité `places`, icône `mdi:parking` ; entité principale |
| `occupancy` | sensor | `{slug}_occupancy` | `%`, `MEASUREMENT`, `suggested_display_precision=0`, icône `mdi:car-multiple` ; indisponible si capacité inconnue |
| `capacity` | sensor | `{slug}_capacity` | `EntityCategory.DIAGNOSTIC`, unité `places` ; non créée si capacité inconnue |
| `full` | binary_sensor | `{slug}_full` | `on` si `occupancy >= seuil` ; indisponible si capacité inconnue ; icônes `mdi:parking` / `mdi:car-off` |

`slug = homeassistant.util.slugify(nom)`. Exemple : `saint_laud_2_available_spaces`.

**Attributs de `available_spaces`** : `latitude`, `longitude` (le parking apparaît sur la carte HA),
`address`, `url`, `max_height_m`, `structure_type`, `free`, `pmr_spaces`, `ev_chargers`, `rate_1h`, `rate_2h`, `rate_3h`, `rate_4h`, `rate_24h`.
→ Ces attributs sont tous statiques : on les déclare dans `_unrecorded_attributes` pour ne pas gonfler la base du recorder.

**Appareil « Open data Angers »** (service), unique :

| translation_key | Plateforme | Unique ID | Détails |
|---|---|---|---|
| `stale_data` | binary_sensor | `stale_data` | `device_class=PROBLEM`, `EntityCategory.DIAGNOSTIC`, attribut `last_change` |

### 5.6 Configuration (`config_flow.py`)

**Instance unique** (`single_config_entry` dans le manifest).

**Étape `user`** :
1. Appel de `async_get_availability()` et chargement de `parkings.json`.
   En cas d'échec, on réaffiche le formulaire avec l'erreur `cannot_connect`.
2. Formulaire :
   - `parkings` : `SelectSelector(multiple=True, mode=LIST)`. Les options sont les `nom` reçus, avec le nom grand public en libellé, triées par libellé. **Toutes cochées par défaut.**
   - `scan_interval` : `NumberSelector(min=1, max=60, step=1, unit="min", mode=BOX)`, défaut 10.
   - `full_threshold` : `NumberSelector(min=50, max=100, step=1, unit="%", mode=SLIDER)`, défaut 95.
3. Validation : au moins 1 parking coché, sinon erreur `no_parking_selected`.
4. `async_create_entry(title="Parking Angers", data={}, options={...})`. Tout est mis dans `options` pour pouvoir le modifier ensuite.

**Options** (`OptionsFlowWithReload`) : le même formulaire, pré-rempli. La liste réunit les `nom` du dernier rafraîchissement et ceux déjà sélectionnés, ce qui évite de perdre une sélection si un parking disparaît temporairement.
- Après rechargement, on **supprime du registre les appareils** des parkings décochés : `device_registry.async_update_device(..., remove_config_entry_id=entry.entry_id)` au setup.

**Clés de traduction** : `config.step.user.{title,description,data,data_description}`,
`config.error.{cannot_connect,no_parking_selected}`, `config.abort.single_instance_allowed`,
`options.step.init.*`, `entity.sensor.{available_spaces,occupancy,capacity}.name`,
`entity.binary_sensor.{full,stale_data}.name`, `issues.stale_data.{title,description}`.
Le texte de `description` de l'étape user mentionne l'attribution : « Données : ALTER / data.angers.fr – licence ODbL ».

### 5.7 Diagnostics (`diagnostics.py`)

Contenu : options de l'entrée, `last_update_success`, horodatage du dernier appel, `stale`, `last_change`,
date de la dernière référence chargée, nombre de parkings, liste des `nom` sans mapping, et dernière réponse brute du temps réel.
Rien de sensible, donc pas de caviardage.

---

## 6. Tests

Outils : `pytest`, `pytest-homeassistant-custom-component`, `aioclient_mock` (fixture HA) ou `aioresponses`, `freezer`.
**Objectif de couverture : 90 % ou plus.**

| Fichier | Cas |
|---|---|
| `test_api.py` | Parsing nominal (fixtures) ; entrée sans `nom` ou `disponible` non entier ; 404/400 → `ResponseError` ; timeout/5xx → `ConnectionError` ; 429 + `X-RateLimit-Reset` → `RateLimitError.retry_after` |
| `test_coordinator.py` | Fusion statique + API (API prioritaire, `null` ignorés) ; référence en échec → secours ; `nom` inconnu ; référence relue après 24 h (freezer) ; détection figée : pas de signal avant 3 h, signal après, retour à la normale quand une valeur change, puis création/suppression du ticket Repairs |
| `test_config_flow.py` | Succès ; `cannot_connect` ; `no_parking_selected` ; instance unique ; options : changement d'intervalle (rechargement), parking décoché → appareil supprimé |
| `test_sensor.py` | Valeurs de places et d'occupation ; bornage si `available > capacity` ; capacité inconnue → occupation indisponible et pas d'entité capacité ; parking absent de la réponse → indisponible ; attributs présents et non enregistrés |
| `test_binary_sensor.py` | `full` de part et d'autre du seuil, et à égalité ; `stale_data` |
| `test_diagnostics.py` | Snapshot (syrupy) |

**`tests/fixtures/realtime_changed.json`** est à créer : une copie de `realtime.json` avec 2 ou 3 valeurs modifiées, pour les tests de détection figée.

---

## 7. Environnement de dev

```bash
uv venv --python 3.13 && source .venv/bin/activate   # aligner sur la version Python requise par HA ciblé
uv pip install -r requirements_test.txt ruff
pytest --cov=custom_components.parking_angers --cov-report=term-missing
ruff check . && ruff format --check .
```

HA local pour les essais manuels :

```yaml
# docker-compose.yml
services:
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    volumes:
      - ./.ha-config:/config
      - ./custom_components:/config/custom_components
    ports: ["8123:8123"]
```

Dans `.ha-config/configuration.yaml`, pour suivre le comportement :

```yaml
logger:
  default: warning
  logs:
    custom_components.parking_angers: debug
```

Ajouter `.ha-config/` et `.venv/` au `.gitignore`.

**CI GitHub Actions** :
- `validate.yml` : `home-assistant/actions/hassfest@master` et `hacs/action@main` (`category: integration`).
- `tests.yml` : ruff puis pytest, sur chaque push et chaque PR.

---

## 8. Jalons

Chaque jalon donne lieu à un commit (ou une PR) testé.

| # | Livrable | Critère de fin |
|---|---|---|
| **M0** | Squelette : `git init`, `pyproject.toml`, `manifest.json`, `hacs.json`, `const.py`, CI, `.gitignore`, README minimal | `hassfest` et `ruff` passent ; l'intégration apparaît dans HA (sans config) |
| **M1** | `api.py`, `models.py`, `scripts/build_parkings_json.py`, `data/parkings.json` | `test_api.py` est vert ; le JSON généré contient 19 entrées, dont Château avec 300 places |
| **M2** | `coordinator.py` (fusion + erreurs, sans la détection figée), `__init__.py` | `test_coordinator.py` (hors figé) est vert |
| **M3** | `config_flow.py` + options + `strings.json` + traductions FR/EN | `test_config_flow.py` est vert ; parcours manuel OK dans HA |
| **M4** | `entity.py`, `sensor.py`, `binary_sensor.py` (`full`), `icons.json` | Entités visibles avec les bons noms FR, et parkings sur la carte HA |
| **M5** | Détection figée + `binary_sensor` `stale_data` + ticket Repairs | Tests freezer verts ; ticket visible dans Paramètres → Réparations |
| **M6** | `diagnostics.py`, README complet (installation, captures, exemple de carte Lovelace, attribution ODbL), tag `v0.1.0` | Couverture ≥ 90 % ; validation HACS verte ; release GitHub |

---

## 9. Hors périmètre v1 / pistes ultérieures

- Persister `last_change` entre les redémarrages (`helpers.storage.Store`).
- Capteur « parking le plus proche ayant de la place » (à partir de `zone.home` ou d'une personne).
- Carte Lovelace dédiée.
- Si le flux reste mort : chercher une autre source (API interne ALTER ?) selon la réponse au mail.
- Soumission à HA core : il faudrait alors sortir `api.py` dans une bibliothèque PyPI et viser l'Integration Quality Scale.

## 10. Risques

| Risque | Impact | Parade |
|---|---|---|
| Flux temps réel figé durablement | L'intégration n'apporte rien | Détection figée + ticket Repairs ; réponse attendue d'ALTER |
| Mapping faux (Mitterrand Rennes, Berges De Maine) | Mauvais nom, capacité ou occupation pour 1 ou 2 parkings | Confirmation ALTER ; correction = une ligne dans les surcharges + regénération |
| Renommage d'un `nom` côté source | Entités orphelines, nouvelles entités créées | Log `info` sur les `nom` inconnus ; note dans le README |
| Changement de schéma de l'API ODS (v2.1 dépréciée) | Plus de données | Surveiller l'en-tête `ODS-Explore-API-Deprecation` : log `warning` s'il est présent |
| Quota partagé (plusieurs instances HA derrière la même IP) | Réponses 429 | `retry_after` ; intervalle minimum de 1 min |
