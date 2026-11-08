"""Tests for the models and the embedded data."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from custom_components.parking_angers.models import (
    ParkingState,
    ParkingStatic,
    load_statics,
)

ROOT = Path(__file__).parent.parent


def test_embedded_data() -> None:
    statics = load_statics()
    assert len(statics) == 19
    assert statics["Chateau"].capacity == 300
    assert statics["Chateau"].ref_id is None
    assert statics["Ralliement"].ref_id == "49007-P-006"
    assert statics["Ralliement"].max_height_m == 1.9
    assert statics["Ralliement"].free is False
    assert statics["Ralliement"].rates["24h"] == 20.0


def test_build_script_is_up_to_date(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "build_parkings_json", ROOT / "scripts" / "build_parkings_json.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    output = tmp_path / "parkings.json"
    sys.argv = ["build", str(ROOT / "tests/fixtures/reference.json"), str(output)]
    module.main()
    embedded = ROOT / "custom_components/parking_angers/data/parkings.json"
    assert json.loads(output.read_text()) == json.loads(embedded.read_text())


def test_merge_ignores_null_values() -> None:
    static = load_statics()["Ralliement"]
    merged = static.merged_with(
        {"nom": "Nouveau nom", "nb_places": None, "tarif_1h": 0.5, "tarif_2h": None}
    )
    assert merged.name == "Nouveau nom"
    assert merged.capacity == 432
    assert merged.rates["1h"] == 0.5
    assert merged.rates["2h"] == 2.0
    assert merged.ref_id == static.ref_id
    assert static.merged_with(None) is static


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"gratuit": "VRAI"}, True),
        ({"gratuit": "FAUX"}, False),
        ({"gratuit": "?"}, None),
    ],
)
def test_free_parsing(raw: dict, expected: bool | None) -> None:
    static = ParkingStatic.unknown("x").merged_with({**raw, "nom": "x"})
    assert static.free is expected


def test_dirty_reference_values() -> None:
    static = ParkingStatic.from_dict(
        "x",
        {
            "capacity": "abc",
            "latitude": "47,5",
            "longitude": True,
            "free": True,
            "name": "  ",
        },
    )
    assert static.capacity is None
    assert static.latitude == 47.5
    assert static.longitude is None
    assert static.free is True
    assert static.name == "x"
    assert ParkingStatic.from_dict("y", {"latitude": "n/a"}).latitude is None


@pytest.mark.parametrize(
    ("capacity", "available", "expected"),
    [
        (100, 25, 75.0),
        (100, 0, 100.0),
        (100, 150, 0.0),
        (None, 10, None),
        (0, 10, None),
    ],
)
def test_occupancy(capacity: int | None, available: int, expected: float | None) -> None:
    static = ParkingStatic(key="x", ref_id=None, name="x", capacity=capacity)
    assert ParkingState(static=static, available=available).occupancy == expected
