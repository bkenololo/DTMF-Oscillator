#!/usr/bin/env python3
"""Regenerate figures from completed CSVs, without running the simulator."""
import csv
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/"src"))
from reporting import charts


def typed(value):
    if value == "":
        return None
    if value in ("True", "False"):
        return value == "True"
    try:
        return float(value)
    except ValueError:
        return value


if __name__ == "__main__":
    results = root/"results"
    cfg = json.loads((results/"config_used.json").read_text())
    summary = json.loads((results/"summary.json").read_text())
    rows = []
    for target in cfg["targets_hz"]:
        with (results/f"simulation_lookup_{target}Hz.csv").open() as file:
            rows += [{k: typed(v) for k, v in row.items()} for row in csv.DictReader(file)]
    charts(rows, summary, cfg, results)
