"""SI units throughout. Analytical results and measured SPICE results stay separate."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
E12 = (10, 12, 15, 18, 22, 27, 33, 39, 47, 56, 68, 82)
E24 = (10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27, 30,
       33, 36, 39, 43, 47, 51, 56, 62, 68, 75, 82, 91)


def network_theory(r1_ohm, r2_ohm, c1_f, c2_f):
    """Ideal, unloaded lead-lag network; R1/C1 series, R2/C2 shunt.

    beta(s) = s R2 C1 / [1+s(R1 C1+R2 C2+R2 C1)+s^2 R1 R2 C1 C2].
    At zero phase: omega^2 R1 R2 C1 C2=1.
    Required non-inverting gain = 1/beta = 1+R1/R2+C2/C1.
    This is NOT an exact prediction of nonlinear circuit oscillation frequency.
    """
    assert min(r1_ohm, r2_ohm, c1_f, c2_f) > 0
    frequency_hz = 1 / (2 * math.pi * math.sqrt(r1_ohm*r2_ohm*c1_f*c2_f))
    required_gain = 1 + r1_ohm/r2_ohm + c2_f/c1_f
    return frequency_hz, required_gain


def preferred_values(series, low_ohm, high_ohm):
    base = E12 if series == "E12" else E24
    return sorted({float(v * 10**decade) for decade in range(-2, 8)
                   for v in base if low_ohm <= v*10**decade <= high_ohm})


def resistor_candidates(target_hz, cfg):
    ideal = 1/(2*math.pi*target_hz*cfg["capacitance_nominal_f"])
    fraction = cfg["resistor_search_fraction"]
    values = preferred_values("E24", ideal*(1-fraction), ideal*(1+fraction))
    e12 = set(preferred_values("E12", ideal*(1-fraction), ideal*(1+fraction)))
    result = [{"ohm": v, "parts_ohm": [v],
               "series": "E12/E24" if v in e12 else "E24"} for v in values]
    if cfg["include_partner_series_combinations"]:
        parts = {770: [20000, 680], 1209: [13000, 150]}.get(target_hz)
        if parts:
            result.append({"ohm": float(sum(parts)), "parts_ohm": parts,
                           "series": "two E24 resistors in series"})
    return sorted(result, key=lambda x: x["ohm"])


def physical_key(row):
    return tuple(row[k] for k in ("target_hz", "R1_ohm", "R2_ohm", "C1_f", "C2_f"))


def make_rows(cfg):
    rows = []
    cap_f = cfg["capacitance_nominal_f"]
    startup_gain = 1+(cfg["gain_feedback_fixed_ohm"]+
                      cfg["gain_feedback_bypassed_ohm"])/cfg["gain_ground_resistance_ohm"]
    limit_gain = 1+cfg["gain_feedback_fixed_ohm"]/cfg["gain_ground_resistance_ohm"]
    for target in cfg["targets_hz"]:
        candidates = resistor_candidates(target, cfg)
        for tol in cfg["capacitance_tolerances_fraction"]:
            for r1, r2, l1, l2 in itertools.product(candidates, candidates,
                    cfg["capacitance_sweep_levels"], cfg["capacitance_sweep_levels"]):
                c1, c2 = cap_f*(1+tol*l1), cap_f*(1+tol*l2)
                freq, req = network_theory(r1["ohm"], r2["ohm"], c1, c2)
                row = dict(target_hz=target, cap_tolerance_percent=tol*100,
                    C_nominal_f=cap_f, C1_offset_percent=tol*l1*100,
                    C2_offset_percent=tol*l2*100, C1_f=c1, C2_f=c2,
                    R1_ohm=r1["ohm"], R2_ohm=r2["ohm"],
                    R1_parts_ohm=" + ".join(f"{x:g}" for x in r1["parts_ohm"]),
                    R2_parts_ohm=" + ".join(f"{x:g}" for x in r2["parts_ohm"]),
                    R1_value_series=r1["series"], R2_value_series=r2["series"],
                    resistor_count=len(r1["parts_ohm"])+len(r2["parts_ohm"]),
                    theory_zero_phase_hz=freq,
                    theory_signed_error_percent=100*(freq-target)/target,
                    theory_abs_error_percent=100*abs(freq-target)/target,
                    theory_required_gain=req, small_signal_gain=startup_gain,
                    theory_small_signal_loop_gain=startup_gain/req,
                    theory_gain_control_brackets_required=(limit_gain < req < startup_gain),
                    capacitors_nominal=(l1 == 0 and l2 == 0))
                key = json.dumps(physical_key(row), separators=(",", ":"))
                row["case_id"] = f"f{target}_"+hashlib.sha256(key.encode()).hexdigest()[:12]
                rows.append(row)
    return rows


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_netlist(row, cfg, folder, model_root=None):
    """Each selected series combination is represented by its physical resistors."""
    model_root = Path(os.path.relpath(model_root or ROOT/"models", folder))
    rlines = []
    for name, start, end in (("R1", "out", "series_rc"), ("R2", "wien", "0")):
        parts = [float(v) for v in row[f"{name}_parts_ohm"].split(" + ")]
        for idx, resistance in enumerate(parts):
            a = start if idx == 0 else f"{name}_junction{idx}"
            b = end if idx == len(parts)-1 else f"{name}_junction{idx+1}"
            rlines.append(f"{name}_{idx+1} {a} {b} {resistance:.14g}")
    load = "* No external output load; only oscillator feedback networks."
    if cfg["output_load_ohm"] is not None:
        load = f"Rload out 0 {cfg['output_load_ohm']:.14g}"
    start, duration = cfg["seed_start_s"], cfg["seed_duration_s"]
    text = f"""Wien oscillator {row['target_hz']} Hz / {row['case_id']}
* R1 is SERIES WIEN resistance; R2 is SHUNT WIEN resistance.
* The TL074 .301 subcircuit uses (+, -, V+, V-, out), NOT DIP pin numbers.
.include "{model_root / 'TL074_ngspice.lib'}"
.include "{model_root / '1N4148.lib'}"
Vpositive vcc 0 DC {cfg['supply_magnitude_v']:.14g}
Vnegative vee 0 DC {-cfg['supply_magnitude_v']:.14g}
Xop wien inv vcc vee out TL074
{chr(10).join(rlines)}
C1 series_rc wien {row['C1_f']:.14g}
C2 wien 0 {row['C2_f']:.14g}
Rg inv 0 {cfg['gain_ground_resistance_ohm']:.14g}
Rf_fixed out diode_junction {cfg['gain_feedback_fixed_ohm']:.14g}
Rf_bypassed diode_junction inv {cfg['gain_feedback_bypassed_ohm']:.14g}
Xdpositive diode_junction inv 1N4148
Xdnegative inv diode_junction 1N4148
{load}
* Finite startup seed, zero after {start+duration+1e-6:.14g} s. Not a sine source.
Iseed 0 wien PWL(0 0 {start:.14g} 0 {start+1e-6:.14g} {cfg['seed_current_a']:.14g} {start+duration:.14g} {cfg['seed_current_a']:.14g} {start+duration+1e-6:.14g} 0)
.temp {cfg['temperature_c']:.14g}
.options reltol=1e-5 abstol=1e-10 vntol=1e-7 method=trap
.save v(out)
.tran {cfg['maximum_time_step_s']:.14g} {cfg['transient_stop_s']:.14g} 0 {cfg['maximum_time_step_s']:.14g}
.end
"""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/"circuit.cir"
    path.write_text(text)
    return path


def read_raw(path):
    content = Path(path).read_bytes()
    marker = b"Binary:\n"
    if marker not in content:
        raise ValueError("Expected ngspice binary transient raw file")
    header, binary = content.split(marker, 1)
    header = header.decode("ascii", errors="replace")
    nvars = int(re.search(r"No\. Variables:\s*(\d+)", header).group(1))
    npoints = int(re.search(r"No\. Points:\s*(\d+)", header).group(1))
    if nvars != 2 or "real" not in header:
        raise ValueError(f"Expected real time and output only, got {header}")
    data = np.frombuffer(binary, dtype=np.float64)
    if data.size != nvars*npoints:
        raise ValueError("Raw file size does not agree with header")
    data = data.reshape(npoints, nvars)
    t, v = data[:, 0].copy(), data[:, 1].copy()
    assert np.all(np.isfinite(data)) and np.all(np.diff(t) >= 0)
    # ngspice can repeat an initial time; keep only strictly advancing entries.
    keep = np.r_[True, np.diff(t) > 0]
    return t[keep], v[keep]


def frequency_from_crossings(time_s, voltage_v):
    centered = voltage_v - np.mean(voltage_v)
    idx = np.flatnonzero((centered[:-1] <= 0) & (centered[1:] > 0))
    if len(idx) < 10:
        return None
    crossing = time_s[idx] - centered[idx]*(time_s[idx+1]-time_s[idx])/(centered[idx+1]-centered[idx])
    periods = np.diff(crossing)
    return 1/float(np.median(periods))


def harmonic_fit(t, v, frequency_hz, harmonics):
    """Least-squares sinusoidal fit avoids treating FFT bin leakage as THD."""
    columns = [np.ones_like(t)]
    for h in range(1, harmonics+1):
        phase = 2*math.pi*h*frequency_hz*(t-t[0])
        columns.extend((np.sin(phase), np.cos(phase)))
    design = np.column_stack(columns)
    coef, _, _, _ = np.linalg.lstsq(design, v, rcond=None)
    amplitudes = np.hypot(coef[1::2], coef[2::2])
    thd = 100*np.sqrt(np.sum(amplitudes[1:]**2))/amplitudes[0]
    residual_rms = np.sqrt(np.mean((v-design@coef)**2))
    return float(thd), float(amplitudes[0]), float(residual_rms), float(coef[0])


def analyze(t, v, row, cfg):
    stop, window = cfg["transient_stop_s"], cfg["analysis_window_s"]
    if t[-1] < stop*(1-1e-5):
        raise ValueError("Transient did not reach configured end time")
    mask = t >= stop-window
    ta, va = t[mask], v[mask]
    mid = stop-window/2
    earlier = va[ta < mid]
    later = va[ta >= mid]
    vpp = float(np.ptp(va))
    amplitude_change = abs(float(np.ptp(later))-float(np.ptp(earlier)))/max(vpp, 1e-12)
    result = dict(simulation_status="ok", oscillation_status="no_sustained_oscillation",
        simulated_frequency_hz=None, simulated_signed_error_percent=None,
        simulated_abs_error_percent=None, steady_state_vpp_v=vpp,
        steady_state_dc_v=float(np.mean(va)), envelope_change_fraction=amplitude_change,
        thd_2_to_10_percent=None, fundamental_peak_v=None, harmonic_fit_residual_rms_v=None,
        settling_time_s=None, maximum_abs_output_v=float(np.max(np.abs(v))),
        output_near_supply_rail=bool(np.max(np.abs(va)) >= 0.95*cfg["supply_magnitude_v"]))
    if vpp < cfg["minimum_peak_to_peak_v"]:
        return result
    freq = frequency_from_crossings(ta, va)
    if freq is None:
        result["oscillation_status"] = "nonperiodic_or_dc"
        return result
    result.update(simulated_frequency_hz=freq,
        simulated_signed_error_percent=100*(freq-row["target_hz"])/row["target_hz"],
        simulated_abs_error_percent=100*abs(freq-row["target_hz"])/row["target_hz"])
    stable = amplitude_change <= cfg["settling_relative_vpp_limit"]
    result["oscillation_status"] = "settled_oscillation" if stable else "not_settled_within_run"
    if not stable:
        return result
    # Use regular samples only for fitting/FFT, retaining the native time trace elsewhere.
    sample_s = cfg["maximum_time_step_s"]
    uniform_t = np.arange(stop-window, stop, sample_s)
    uniform_v = np.interp(uniform_t, t, v)
    # Downsample fitting to <=5000 samples while retaining >20 samples at harmonic 10.
    stride = max(1, len(uniform_t)//5000)
    thd, amp, residual, dc = harmonic_fit(uniform_t[::stride], uniform_v[::stride], freq,
                                    cfg["harmonics_for_thd"])
    result.update(thd_2_to_10_percent=thd, fundamental_peak_v=amp, steady_state_dc_v=dc,
                  harmonic_fit_residual_rms_v=residual)
    # Settling: first 10 ms bin after which every bin Vpp stays within 2% of final Vpp.
    edges = np.arange(0, stop+0.005, 0.01)
    bins = [np.ptp(v[(t >= a) & (t < b)]) for a, b in zip(edges[:-1], edges[1:])]
    within = np.abs(np.asarray(bins)-vpp) <= cfg["settling_relative_vpp_limit"]*vpp
    for idx in range(len(within)-5):
        if np.all(within[idx:]):
            result["settling_time_s"] = float(edges[idx+1])
            break
    return result


def fingerprint(cfg, row, executable):
    digest = hashlib.sha256()
    digest.update(json.dumps(cfg, sort_keys=True).encode())
    digest.update(json.dumps(physical_key(row)).encode())
    digest.update(Path(__file__).read_bytes())
    for file in ("TL074_ngspice.lib", "1N4148.lib"):
        digest.update((ROOT/"models"/file).read_bytes())
    digest.update(subprocess.check_output([executable, "--version"], stderr=subprocess.STDOUT))
    return digest.hexdigest()


def run_case(row, cfg, executable, results_root, force=False, keep_raw=False):
    folder = results_root/"cases"/row["case_id"]
    folder.mkdir(parents=True, exist_ok=True)
    stamp = fingerprint(cfg, row, executable)
    cache = folder/"metrics.json"
    if cache.exists() and not force:
        old = json.loads(cache.read_text())
        if old.get("fingerprint") == stamp and old.get("simulation_status") == "ok":
            return old
    netlist = write_netlist(row, cfg, folder)
    raw = folder/"waveform.raw"
    log = folder/"ngspice.log"
    start = time.perf_counter()
    try:
        env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
        env["SPICE_ASCIIRAWFILE"] = "0"
        # Local simulator stays usable after moving this project folder. Load its
        # XSPICE POLY code model through a project-generated startup file.
        local_lib = Path(executable).parent.parent/"lib"/"ngspice"
        if (local_lib/"spice2poly.cm").exists():
            # A local alias avoids ngspice command-parser issues with spaces in paths.
            alias = folder/"spice2poly.cm"
            alias.unlink(missing_ok=True)
            try:
                alias.symlink_to((local_lib/"spice2poly.cm").resolve())
            except OSError:
                shutil.copyfile(local_lib/"spice2poly.cm", alias)
            lines = ["* Generated startup: only POLY support required by TL074.301",
                     "set filetype=binary", "set num_threads=1",
                     'codemodel ./spice2poly.cm']
            (folder/"spinit").write_text("\n".join(lines)+"\n")
            env["SPICE_SCRIPTS"] = str(folder)
        # -n avoids reading user .spiceinit; explicit raw output is binary by default.
        proc = subprocess.run([executable, "-n", "-b", "-r", raw.name, "-o", log.name,
                               netlist.name], cwd=folder, env=env,
                              capture_output=True, text=True, timeout=cfg["per_case_timeout_s"])
        (folder/"console.log").write_text(proc.stdout+proc.stderr)
        if proc.returncode != 0 or not raw.exists():
            raise RuntimeError(f"ngspice exit {proc.returncode}; inspect {log}")
        t, v = read_raw(raw)
        result = analyze(t, v, row, cfg)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        result = dict(simulation_status="simulation_failed", oscillation_status="unknown",
                      error=str(error))
    result.update(case_id=row["case_id"], fingerprint=stamp,
                  elapsed_wall_s=time.perf_counter()-start)
    cache.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    if raw.exists() and not keep_raw:
        raw.unlink()
    return result


def discover_ngspice(requested=None):
    candidates = [requested, os.environ.get("NGSPICE"),
                  str(ROOT/"tools"/"ngspice"/"bin"/"ngspice"), shutil.which("ngspice")]
    for path in candidates:
        if path and Path(path).is_file() and os.access(path, os.X_OK):
            return str(Path(path).resolve())
    raise SystemExit("ngspice not found. Install it or use --ngspice /absolute/path/to/ngspice")


def validate_config(cfg):
    assert cfg["capacitance_nominal_f"] > 0
    assert all(0 < t < 1 for t in cfg["capacitance_tolerances_fraction"])
    assert all(-1 <= x <= 1 for x in cfg["capacitance_sweep_levels"])
    assert cfg["analysis_window_s"]*2 <= cfg["transient_stop_s"]
    assert 0 < cfg["resistor_search_fraction"] < 1
    assert cfg["maximum_time_step_s"] > 0
    assert cfg["workers"] >= 1
    assert cfg["harmonics_for_thd"] == 10, "Output schema explicitly reports harmonics 2 through 10"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT/"config.json")
    parser.add_argument("--results", type=Path, default=ROOT/"results")
    parser.add_argument("--ngspice")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--theory-only", action="store_true")
    parser.add_argument("--limit", type=int, help="Smoke test only; does NOT complete the full sweep")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    if args.workers:
        cfg["workers"] = args.workers
    validate_config(cfg)
    results = args.results.resolve()
    results.mkdir(parents=True, exist_ok=True)
    (results/"config_used.json").write_text(json.dumps(cfg, indent=2)+"\n")
    rows = make_rows(cfg)
    for target in cfg["targets_hz"]:
        subset = [r for r in rows if r["target_hz"] == target]
        write_csv(results/f"theory_lookup_{target}Hz.csv", subset)
    print(f"Generated {len(rows)} scenario rows", flush=True)
    if args.theory_only:
        return
    executable = discover_ngspice(args.ngspice)
    unique = {r["case_id"]: r for r in rows}
    jobs = list(unique.values())
    if args.limit:
        jobs = jobs[:args.limit]
    print(f"Simulating {len(jobs)} unique physical circuits with {executable}", flush=True)
    measured = {}
    with ThreadPoolExecutor(max_workers=cfg["workers"]) as pool:
        futures = {pool.submit(run_case, r, cfg, executable, results, args.force): r for r in jobs}
        for n, future in enumerate(as_completed(futures), 1):
            row = futures[future]
            measured[row["case_id"]] = future.result()
            if n % 50 == 0 or n == len(jobs):
                errors = sum(v["simulation_status"] != "ok" for v in measured.values())
                print(f"Completed {n}/{len(jobs)} unique circuits; simulator failures {errors}", flush=True)
    joined = [dict(row, **measured[row["case_id"]]) for row in rows if row["case_id"] in measured]
    for target in cfg["targets_hz"]:
        subset = [r for r in joined if r["target_hz"] == target]
        write_csv(results/f"simulation_lookup_{target}Hz.csv", subset)
    from reporting import make_report
    make_report(joined, cfg, results, executable, incomplete=bool(args.limit), no_plots=args.no_plots)
    failures = sum(m["simulation_status"] != "ok" for m in measured.values())
    if failures:
        raise SystemExit(f"{failures} simulator failures retained explicitly in tables/logs")
    print(f"Results saved in {results}", flush=True)
