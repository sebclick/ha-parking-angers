"""Data models for the Parking Angers integration.

This module has no Home Assistant dependency so it can be reused by the
``scripts/build_parkings_json.py`` generator.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
import json
from pathlib import Path
from typing import Any

RATE_KEYS: tuple[str, ...] = ("1h", "2h", "3h", "4h", "24h")


def _to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "."))
    except TypeError, ValueError:
        return None


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        upper = value.strip().upper()
        if upper in ("VRAI", "TRUE", "OUI", "1"):
            return True
        if upper in ("FAUX", "FALSE", "NON", "0"):
            return False
    return None


@dataclass(frozen=True)
class ParkingStatic:
    """Static (reference) information about a car park."""

    key: str
    ref_id: str | None
    name: str
    capacity: int | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    url: str | None = None
    max_height_m: float | None = None
    structure_type: str | None = None
    free: bool | None = None
    pmr_spaces: int | None = None
    ev_chargers: int | None = None
    rates: dict[str, float | None] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, key: str, data: dict[str, Any]) -> ParkingStatic:
        """Build from a ``parkings.json`` entry."""
        rates = data.get("rates") or {}
        return cls(
            key=key,
            ref_id=_to_str(data.get("ref_id")),
            name=_to_str(data.get("name")) or key,
            capacity=_to_int(data.get("capacity")),
            address=_to_str(data.get("address")),
            latitude=_to_float(data.get("latitude")),
            longitude=_to_float(data.get("longitude")),
            url=_to_str(data.get("url")),
            max_height_m=_to_float(data.get("max_height_m")),
            structure_type=_to_str(data.get("structure_type")),
            free=_to_bool(data.get("free")),
            pmr_spaces=_to_int(data.get("pmr_spaces")),
            ev_chargers=_to_int(data.get("ev_chargers")),
            rates={k: _to_float(rates.get(k)) for k in RATE_KEYS},
        )

    @classmethod
    def unknown(cls, key: str) -> ParkingStatic:
        """Build a placeholder for a car park missing from ``parkings.json``."""
        return cls(key=key, ref_id=None, name=key, rates=dict.fromkeys(RATE_KEYS))

    def to_dict(self) -> dict[str, Any]:
        """Serialise as a ``parkings.json`` entry (without the key)."""
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name != "key"}

    def merged_with(self, reference: dict[str, Any] | None) -> ParkingStatic:
        """Return a copy overridden by the non-null values of a raw reference record."""
        if not reference:
            return self
        values = reference_to_fields(reference)
        rates = dict(self.rates)
        for rate_key, rate in values.pop("rates").items():
            if rate is not None:
                rates[rate_key] = rate
        current = self.to_dict()
        current.update({k: v for k, v in values.items() if v is not None})
        current["rates"] = rates
        current["ref_id"] = self.ref_id
        return ParkingStatic(key=self.key, **current)


def reference_to_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw ``angers_stationnement`` record to ParkingStatic fields."""
    height_cm = _to_float(raw.get("hauteur_max"))
    return {
        "name": _to_str(raw.get("nom")),
        "capacity": _to_int(raw.get("nb_places")),
        "address": _to_str(raw.get("adresse")),
        "latitude": _to_float(raw.get("ylat")),
        "longitude": _to_float(raw.get("xlong")),
        "url": _to_str(raw.get("url")),
        "max_height_m": round(height_cm / 100, 2) if height_cm else None,
        "structure_type": _to_str(raw.get("type_ouvrage")),
        "free": _to_bool(raw.get("gratuit")),
        "pmr_spaces": _to_int(raw.get("nb_pmr")),
        "ev_chargers": _to_int(raw.get("nb_voitures_electriques")),
        "rates": {k: _to_float(raw.get(f"tarif_{k}")) for k in RATE_KEYS},
    }


@dataclass(frozen=True)
class ParkingState:
    """Real-time state of a car park."""

    static: ParkingStatic
    available: int

    @property
    def occupancy(self) -> float | None:
        """Occupancy rate in percent (0..100), None if capacity is unknown."""
        capacity = self.static.capacity
        if not capacity or capacity <= 0:
            return None
        return max(0.0, min(100.0, (1 - self.available / capacity) * 100))


@dataclass
class ParkingData:
    """Data held by the coordinator."""

    parkings: dict[str, ParkingState]
    stale: bool = False
    last_change: datetime | None = None


STATIC_FILE = Path(__file__).parent / "data" / "parkings.json"


def load_statics(path: Path = STATIC_FILE) -> dict[str, ParkingStatic]:
    """Load the embedded ``parkings.json`` (blocking I/O)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {key: ParkingStatic.from_dict(key, value) for key, value in raw.items()}
