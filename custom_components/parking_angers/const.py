"""Constants for the Parking Angers integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "parking_angers"
VERSION: Final = "0.1.2"

API_BASE_URL: Final = "https://data.angers.fr/api/explore/v2.1/catalog/datasets"
REALTIME_DATASET: Final = "parking-angers"
REFERENCE_DATASET: Final = "angers_stationnement"
API_LIMIT: Final = 100
API_TIMEOUT: Final = 15
# Largest accepted response body (the reference dataset is about 20 kB).
MAX_RESPONSE_BYTES: Final = 2 * 1024 * 1024
MAX_NAME_LENGTH: Final = 100
USER_AGENT: Final = f"HomeAssistant-ParkingAngers/{VERSION}"
DEPRECATION_HEADER: Final = "ODS-Explore-API-Deprecation"

CONF_PARKINGS: Final = "parkings"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_FULL_THRESHOLD: Final = "full_threshold"

DEFAULT_SCAN_INTERVAL: Final = 10
MIN_SCAN_INTERVAL: Final = 1
MAX_SCAN_INTERVAL: Final = 60

DEFAULT_FULL_THRESHOLD: Final = 95
MIN_FULL_THRESHOLD: Final = 50
MAX_FULL_THRESHOLD: Final = 100

REFERENCE_REFRESH: Final = timedelta(hours=24)
# Upper bound for waiting after a 429 (the anonymous quota resets daily).
MAX_RETRY_AFTER: Final = timedelta(hours=24)
STALE_AFTER: Final = timedelta(hours=3)

ISSUE_STALE_DATA: Final = "stale_data"

MANUFACTURER: Final = "ALTER"
ATTRIBUTION: Final = "Données : ALTER / data.angers.fr - licence ODbL"
SERVICE_DEVICE_ID: Final = "open_data"
