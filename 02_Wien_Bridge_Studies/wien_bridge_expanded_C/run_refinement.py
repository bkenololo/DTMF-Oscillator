#!/usr/bin/env python3
"""Optional finer E24 series-resistor grid, using the exact same simulator core."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/"src"))
import wien


def refinement_candidates(target_hz, cfg):
    spec = cfg["fine_resistor_components_ohm"][str(target_hz)]
    base = spec["base_ohm"]
    rows = []
    for extra in spec["additions_ohm"]:
        rows.append(dict(ohm=float(base+extra), parts_ohm=[base, extra],
                         series="two E24 resistors in series"))
    return sorted(rows, key=lambda r: r["ohm"])


if __name__ == "__main__":
    wien.resistor_candidates = refinement_candidates
    if "--config" not in sys.argv:
        sys.argv += ["--config", str(ROOT/"refinement/config.json")]
    if "--results" not in sys.argv:
        sys.argv += ["--results", str(ROOT/"refinement/results")]
    wien.main()
