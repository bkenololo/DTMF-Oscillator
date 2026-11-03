#!/usr/bin/env python3
"""Regenerate figures from completed CSVs, without running the simulator."""
import csv
import json
import argparse
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/"src"))
from expanded_reporting import charts


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
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=root/'results')
    results = parser.parse_args().results.resolve()
    cfg = json.loads((results/"config_used.json").read_text())
    summary = json.loads((results/"summary.json").read_text())
    rows = []
    for target in cfg["targets_hz"]:
        with (results/f"simulation_lookup_{target}Hz.csv").open() as file:
            rows += [{k: typed(v) for k, v in row.items()} for row in csv.DictReader(file)]
    charts(rows, summary, cfg, results)
