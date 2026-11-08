"""Generate custom_components/parking_angers/data/parkings.json.

Input: tests/fixtures/reference.json (raw ``angers_stationnement`` response) plus
the manual overrides below (real-time ``nom`` -> reference ``id`` mapping and the
Château car park, which is missing from the reference dataset).

Usage: python scripts/build_parkings_json.py [reference.json] [output.json]
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "parking_angers"

_spec = importlib.util.spec_from_file_location(
    "parking_angers_models", COMPONENT / "models.py"
)
models = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = models
_spec.loader.exec_module(models)

# Real-time ``nom`` -> reference ``id``. See PLAN.md § 3.
MAPPING: dict[str, str] = {
    "Berges De Maine": "49007-P-001",  # medium confidence
    "Mitterrand Rennes": "49007-P-002",  # to be confirmed (by elimination)
    "Republique": "49007-P-003",
    "Confluences": "49007-P-004",
    "Saint Laud 2": "49007-P-005",
    "Ralliement": "49007-P-006",
    "Mitterrand Maine": "49007-P-007",
    "Larrey": "49007-P-008",
    "Bressigny": "49007-P-009",
    "Mail": "49007-P-010",
    "Saint Laud": "49007-P-011",
    "Haras Public": "49007-P-012",
    "Saint Serge Patinoire": "49007-P-013",
    "Moliere": "49007-P-014",
    "Leclerc": "49007-P-015",
    "Marengo": "49007-P-016",
    "Quai": "49007-P-017",
    "Maternite": "49007-P-018",
}

# Car parks absent from the reference dataset, entered by hand.
MANUAL: dict[str, dict] = {
    "Chateau": {
        "ref_id": None,
        "name": "Parking du Château",
        "capacity": 300,
        "address": "Rue de Quatrebarbes, 49100 Angers",
        # Approximate: street geocoded with api-adresse.data.gouv.fr
        "latitude": 47.46892,
        "longitude": -0.561197,
        "url": "https://parking-angers.fr/parking/parking-chateau/",
        "max_height_m": 1.9,
        "structure_type": "ouvrage",
        "free": False,
        "pmr_spaces": 6,
        "ev_chargers": None,
        "rates": dict.fromkeys(models.RATE_KEYS),
    },
}


def build(reference_path: Path) -> dict[str, dict]:
    raw = json.loads(reference_path.read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in raw["results"] if r.get("id")}
    out: dict[str, dict] = {}
    for key, ref_id in MAPPING.items():
        if ref_id not in by_id:
            raise SystemExit(f"{ref_id} (for {key!r}) not found in {reference_path}")
        base = models.ParkingStatic.from_dict(key, {"ref_id": ref_id})
        out[key] = base.merged_with(by_id[ref_id]).to_dict()
    for key, data in MANUAL.items():
        out[key] = models.ParkingStatic.from_dict(key, data).to_dict()
    unused = set(by_id) - set(MAPPING.values())
    if unused:
        print(f"Warning: reference ids not mapped: {sorted(unused)}", file=sys.stderr)
    return dict(sorted(out.items()))


def main() -> None:
    reference = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "tests/fixtures/reference.json"
    )
    output = (
        Path(sys.argv[2]) if len(sys.argv) > 2 else COMPONENT / "data/parkings.json"
    )
    data = build(reference)
    output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(data)} car parks to {output}")


if __name__ == "__main__":
    main()
