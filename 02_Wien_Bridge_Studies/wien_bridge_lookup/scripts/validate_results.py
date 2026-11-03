#!/usr/bin/env python3
"""Validate completed CSV coverage and provenance using only Python's standard library."""
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path

root = Path(__file__).resolve().parents[1]
results = root/"results"
cfg = json.loads((results/"config_used.json").read_text())
provenance = json.loads((root/"models/provenance.json").read_text())
assert hashlib.sha256((root/"models/TL074.301").read_bytes()).hexdigest() == provenance["original_sha256"]
assert hashlib.sha256((root/"models/TL074_ngspice.lib").read_bytes()).hexdigest() == provenance["normalized_sha256"]
assert hashlib.sha256((root/"models/1N4148.lib").read_bytes()).hexdigest() == provenance["diode_model_sha256"]
all_ids = set()
report = {"models_match_recorded_hashes": True, "oscillators": {}}
for target in cfg["targets_hz"]:
    with (results/f"simulation_lookup_{target}Hz.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 675
    assert Counter(float(r["cap_tolerance_percent"]) for r in rows) == {1.:225, 5.:225, 10.:225}
    ids = {r["case_id"] for r in rows}
    assert len(ids) == 625
    all_ids |= ids
    for row in rows:
        r1, r2, c1, c2 = (float(row[k]) for k in ("R1_ohm", "R2_ohm", "C1_f", "C2_f"))
        calculated = 1/(2*math.pi*math.sqrt(r1*r2*c1*c2))
        assert math.isclose(calculated, float(row["theory_zero_phase_hz"]), rel_tol=1e-12)
        assert row["simulation_status"] == "ok"
        if row["oscillation_status"] == "settled_oscillation":
            measured = float(row["simulated_frequency_hz"])
            assert measured > 0
            assert math.isclose(float(row["simulated_abs_error_percent"]),
                                100*abs(measured-target)/target, rel_tol=1e-10, abs_tol=1e-10)
            assert float(row["thd_2_to_10_percent"]) >= 0
        folder = results/"cases"/row["case_id"]
        assert (folder/"circuit.cir").is_file() and (folder/"ngspice.log").is_file()
        metrics = json.loads((folder/"metrics.json").read_text())
        assert metrics["simulation_status"] == "ok"
        if row["simulated_frequency_hz"]:
            assert float(row["simulated_frequency_hz"]) == metrics["simulated_frequency_hz"]
    report["oscillators"][str(target)] = dict(scenario_rows=len(rows), unique_physical_circuits=len(ids),
        rows_per_tolerance=225, simulator_failures=0,
        statuses=dict(Counter(r["oscillation_status"] for r in rows)))
assert len(all_ids) == 1250
summary = json.loads((results/"summary.json").read_text())
assert summary["incomplete"] is False
for check in summary["timestep_checks"]:
    assert check["simulation_status"] == "ok"
    assert check["original_status"] == check["refined_status"] == "settled_oscillation"
report["unique_physical_circuits"] = len(all_ids)
report["total_scenario_rows"] = 1350
report["numerical_checks"] = summary["timestep_checks"]
(results/"validation.json").write_text(json.dumps(report, indent=2)+"\n")
print("Validated 1350 rows, 1250 actual circuit runs, model hashes, case evidence, and timestep checks.")
