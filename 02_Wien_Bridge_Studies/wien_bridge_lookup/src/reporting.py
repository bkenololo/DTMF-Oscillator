"""Human-readable reports and charts from actual measured ngspice sweeps."""
from __future__ import annotations
from collections import Counter
import html
import json
import math
from pathlib import Path

import numpy as np


def nominal_ranking(rows):
    seen = {}
    for row in rows:
        if row["capacitors_nominal"]:
            seen[row["case_id"]] = row
    return sorted(seen.values(), key=lambda r: (
        r.get("oscillation_status") != "settled_oscillation",
        r.get("simulated_abs_error_percent") if r.get("simulated_abs_error_percent") is not None else math.inf,
        r["resistor_count"]))


def tolerance_ranking(rows, cfg):
    groups = {}
    for r in rows:
        key = (r["target_hz"], r["cap_tolerance_percent"], r["R1_ohm"], r["R2_ohm"])
        groups.setdefault(key, []).append(r)
    result = []
    expected = len(cfg["capacitance_sweep_levels"])**2
    for (target, tol, r1, r2), cases in groups.items():
        stable = [r for r in cases if r.get("oscillation_status") == "settled_oscillation"]
        result.append(dict(target_hz=target, cap_tolerance_percent=tol, R1_ohm=r1, R2_ohm=r2,
            simulated_grid_points=len(cases), expected_grid_points=expected,
            settled_grid_points=len(stable), all_sampled_points_settled=(len(stable) == expected),
            minimum_frequency_hz=min((r["simulated_frequency_hz"] for r in stable), default=None),
            maximum_frequency_hz=max((r["simulated_frequency_hz"] for r in stable), default=None),
            worst_sampled_abs_error_percent=max((r["simulated_abs_error_percent"] for r in stable), default=None),
            worst_sampled_thd_percent=max((r["thd_2_to_10_percent"] for r in stable), default=None)))
    result.sort(key=lambda r: (r["target_hz"], r["cap_tolerance_percent"],
        not r["all_sampled_points_settled"], -r["settled_grid_points"],
        r["worst_sampled_abs_error_percent"] if r["worst_sampled_abs_error_percent"] is not None else math.inf))
    return result


def inspect_representative(row, cfg, results, executable):
    from wien import read_raw, run_case, write_csv
    # Separate paths prevent diagnostic reruns from replacing the sweep evidence.
    folder = results/"representatives"/f"{row['target_hz']}Hz"
    measurement = run_case(row, cfg, executable, folder, force=True, keep_raw=True)
    if measurement["simulation_status"] != "ok":
        return dict(simulation_status="simulation_failed", error=measurement.get("error"))
    case_folder = folder/"cases"/row["case_id"]
    t, v = read_raw(case_folder/"waveform.raw")
    np.savez_compressed(folder/"trace.npz", time_s=t, output_v=v)
    # A compact, portable CSV for import into other plotting programs.
    selection = np.unique(np.r_[np.arange(0, len(t), 20), np.flatnonzero(t >= cfg["transient_stop_s"]-0.015)])
    np.savetxt(folder/"trace_excerpt.csv", np.column_stack((t[selection], v[selection])),
               delimiter=",", header="time_s,output_v", comments="")
    (case_folder/"waveform.raw").unlink()
    refined_cfg = dict(cfg, maximum_time_step_s=cfg["maximum_time_step_s"]/2)
    refined = run_case(row, refined_cfg, executable, folder/"half_timestep", force=True)
    check = dict(target_hz=row["target_hz"], R1_ohm=row["R1_ohm"], R2_ohm=row["R2_ohm"],
        original_maximum_timestep_s=cfg["maximum_time_step_s"],
        refined_maximum_timestep_s=refined_cfg["maximum_time_step_s"],
        original_frequency_hz=measurement.get("simulated_frequency_hz"),
        refined_frequency_hz=refined.get("simulated_frequency_hz"),
        original_vpp_v=measurement.get("steady_state_vpp_v"),
        refined_vpp_v=refined.get("steady_state_vpp_v"),
        original_thd_percent=measurement.get("thd_2_to_10_percent"),
        refined_thd_percent=refined.get("thd_2_to_10_percent"),
        original_status=measurement.get("oscillation_status"),
        refined_status=refined.get("oscillation_status"),
        simulation_status=refined.get("simulation_status"))
    if refined.get("simulated_frequency_hz") and measurement.get("simulated_frequency_hz"):
        check["frequency_change_percent"] = 100*abs(refined["simulated_frequency_hz"]-measurement["simulated_frequency_hz"])/refined["simulated_frequency_hz"]
    return check


def charts(rows, summary, cfg, results):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    figures = results/"figures"
    figures.mkdir(exist_ok=True)
    for target in cfg["targets_hz"]:
        selected = summary["oscillators"][str(target)].get("best_nominal_any_pair")
        if selected:
            trace = np.load(results/"representatives"/f"{target}Hz"/"trace.npz")
            t, v = trace["time_s"], trace["output_v"]
            fig, axes = plt.subplots(3, 1, figsize=(10, 8), constrained_layout=True)
            axes[0].plot(t[::10]*1000, v[::10], lw=0.6, color="#135f94")
            axes[0].set(xlabel="Time (ms)", ylabel="Output (V)", title="Startup and amplitude settling")
            end = t[-1]
            tail = t >= end-0.012
            axes[1].plot((t[tail]-end+0.012)*1000, v[tail], color="#135f94")
            axes[1].set(xlabel="Time within final 12 ms", ylabel="Output (V)", title="Settled waveform")
            dt = cfg["maximum_time_step_s"]
            uniform = np.arange(end-cfg["analysis_window_s"], end, dt)
            signal = np.interp(uniform, t, v)
            signal -= np.mean(signal)
            window = np.hanning(len(signal))
            spectrum = 2*np.abs(np.fft.rfft(signal*window))/window.sum()
            f = np.fft.rfftfreq(len(signal), dt)
            db = 20*np.log10(np.maximum(spectrum, 1e-12)/np.max(spectrum))
            axes[2].plot(f, db, color="#135f94", lw=0.9)
            axes[2].axvline(target, color="#ac3025", ls="--", lw=0.8, label=f"Target {target} Hz")
            axes[2].set(xlabel="Frequency (Hz)", ylabel="Magnitude (dBc)", xlim=(0, 10.5*target),
                        ylim=(-100, 5), title=f"Hann-window FFT, bin spacing {1/cfg['analysis_window_s']:g} Hz")
            axes[2].legend(loc="upper right")
            fig.suptitle(f"{target} Hz Wien oscillator: R1 = {selected['R1_ohm']/1000:g} kΩ; R2 = {selected['R2_ohm']/1000:g} kΩ\n"
                f"ngspice: {selected['simulated_frequency_hz']:.3f} Hz, {selected['steady_state_vpp_v']:.3f} Vpp, "
                f"THD (2–10) {selected['thd_2_to_10_percent']:.3f}%")
            fig.savefig(figures/f"oscillator_{target}Hz.png", dpi=150)
            plt.close(fig)
        nominal = nominal_ranking([r for r in rows if r["target_hz"] == target])
        resistances = sorted(set(r["R1_ohm"] for r in nominal))
        matrix = np.full((len(resistances), len(resistances)), np.nan)
        for row in nominal:
            if row.get("oscillation_status") == "settled_oscillation":
                matrix[resistances.index(row["R2_ohm"]), resistances.index(row["R1_ohm"])] = row["simulated_signed_error_percent"]
        fig, ax = plt.subplots(figsize=(8, 6), constrained_layout=True)
        bound = max(1.0, float(np.nanmax(np.abs(matrix)))) if np.any(np.isfinite(matrix)) else 1.0
        color = plt.get_cmap("RdBu_r").copy()
        color.set_bad("#dddddd")
        im = ax.imshow(matrix, origin="lower", cmap=color, vmin=-bound, vmax=bound)
        labels = [f"{r/1000:g}" for r in resistances]
        ax.set_xticks(range(len(labels)), labels)
        ax.set_yticks(range(len(labels)), labels)
        for y, x in np.ndindex(matrix.shape):
            value = matrix[y, x]
            ax.text(x, y, f"{value:+.2f}%" if np.isfinite(value) else "No settled\noscillation",
                    ha="center", va="center", fontsize=9,
                    color="white" if np.isfinite(value) and abs(value) > 0.6*bound else "black")
        ax.set(xlabel="Series Wien resistance R1 (kΩ)", ylabel="Shunt Wien resistance R2 (kΩ)",
               title=f"{target} Hz: independently swept resistors\nNominal C1 = C2 = 10 nF; gray cells did not settle")
        fig.colorbar(im, ax=ax, label="Simulated frequency error (%)")
        fig.savefig(figures/f"resistor_sweep_{target}Hz.png", dpi=150)
        plt.close(fig)
        if selected:
            fig, axes = plt.subplots(1, 3, figsize=(13, 5))
            fig.subplots_adjust(left=0.055, right=0.88, bottom=0.17, top=0.76, wspace=0.30)
            for ax, tolerance in zip(axes, cfg["capacitance_tolerances_fraction"]):
                samples = [r for r in rows if r["target_hz"] == target
                    and abs(r["cap_tolerance_percent"]-100*tolerance) < 1e-9
                    and r["R1_ohm"] == selected["R1_ohm"] and r["R2_ohm"] == selected["R2_ohm"]]
                offsets = sorted(set(r["C1_offset_percent"] for r in samples))
                matrix, freqs = np.full((3, 3), np.nan), np.full((3, 3), np.nan)
                for row in samples:
                    if row.get("oscillation_status") == "settled_oscillation":
                        y, x = offsets.index(row["C2_offset_percent"]), offsets.index(row["C1_offset_percent"])
                        matrix[y, x] = row["simulated_signed_error_percent"]
                        freqs[y, x] = row["simulated_frequency_hz"]
                im = ax.imshow(matrix, origin="lower", cmap=color, vmin=-13, vmax=13)
                ticks = [f"{cfg['capacitance_nominal_f']*(1+x/100)*1e9:g}" for x in offsets]
                ax.set_xticks(range(3), ticks)
                ax.set_yticks(range(3), ticks)
                ax.set(xlabel="C1 (nF)", ylabel="C2 (nF)", title=f"±{100*tolerance:g}% tolerance")
                for y, x in np.ndindex(matrix.shape):
                    ax.text(x, y, f"{freqs[y,x]:.1f} Hz\n{matrix[y,x]:+.2f}%" if np.isfinite(matrix[y,x]) else "No settled\noscillation",
                            ha="center", va="center", fontsize=8,
                            color="white" if np.isfinite(matrix[y,x]) and abs(matrix[y,x])>8 else "black")
            colorbar_axes = fig.add_axes([0.91, 0.18, 0.016, 0.57])
            fig.colorbar(im, cax=colorbar_axes, label="Simulated frequency error (%)")
            fig.suptitle(f"{target} Hz: independent capacitor tolerance sweep at closest nominal resistor pair\n"
                         f"R1 = {selected['R1_ohm']/1000:g} kΩ, R2 = {selected['R2_ohm']/1000:g} kΩ; C nominal = 10 nF")
            fig.savefig(figures/f"capacitor_sweep_{target}Hz.png", dpi=150)
            plt.close(fig)


def make_report(rows, cfg, results, executable, incomplete=False, no_plots=False):
    import subprocess
    from wien import write_csv
    summary = dict(scope="Two independent oscillators; no summing amplifier yet", incomplete=incomplete,
        scenario_rows=len(rows), unique_physical_circuits=len({r["case_id"] for r in rows}),
        ngspice_version=subprocess.check_output([executable, "--version"], text=True).strip(),
        primary_cap_tolerance_percent=cfg["primary_capacitance_tolerance_fraction"]*100,
        oscillators={})
    comparisons = tolerance_ranking(rows, cfg)
    write_csv(results/"tolerance_comparison.csv", comparisons)
    selected_keys = ("case_id", "R1_ohm", "R2_ohm", "R1_parts_ohm", "R2_parts_ohm",
        "simulated_frequency_hz", "simulated_abs_error_percent", "steady_state_vpp_v",
        "thd_2_to_10_percent", "settling_time_s", "resistor_count")
    checks = []
    for target in cfg["targets_hz"]:
        subset = [r for r in rows if r["target_hz"] == target]
        ranking = nominal_ranking(subset)
        write_csv(results/f"nominal_candidates_{target}Hz.csv", ranking)
        stable = [r for r in ranking if r.get("oscillation_status") == "settled_oscillation"]
        balanced = [r for r in stable if r["R1_ohm"] == r["R2_ohm"]]
        best = balanced[0] if balanced else None
        info = dict(scenario_rows=len(subset), unique_physical_circuits=len({r["case_id"] for r in subset}),
            status_counts=dict(Counter(r.get("oscillation_status") for r in subset)),
            simulator_failures=sum(r.get("simulation_status") != "ok" for r in subset),
            best_nominal_any_pair={k: stable[0].get(k) for k in selected_keys} if stable else None,
            best_balanced_nominal={k: best.get(k) for k in selected_keys} if best else None)
        summary["oscillators"][str(target)] = info
        if stable:
            selected = stable[0]
            checks.append(inspect_representative(selected, cfg, results, executable))
            from wien import write_netlist
            write_netlist(selected, cfg, results.parent/"circuits"/f"selected_{target}Hz")
    write_csv(results/"timestep_convergence.csv", checks)
    summary["timestep_checks"] = checks
    (results/"summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n")
    (results/"selected_nominal_values.json").write_text(json.dumps({
        "selection_rule": "Smallest nominal simulated frequency error among settled resistor pairs in this finite search; not a guarantee across capacitor tolerance.",
        "C1_nominal_f": cfg["capacitance_nominal_f"], "C2_nominal_f": cfg["capacitance_nominal_f"],
        "primary_cap_tolerance_percent": 100*cfg["primary_capacitance_tolerance_fraction"],
        "oscillators": {str(t): summary["oscillators"][str(t)]["best_nominal_any_pair"] for t in cfg["targets_hz"]}
    }, indent=2)+"\n")
    if not no_plots:
        charts(rows, summary, cfg, results)
    report = ["# Independent Wien bridge oscillator results", "",
        "These are ngspice transient measurements using the supplied TL074.301 model. "
        "This stage has no summing amplifier or external output load.", "",
        f"Scenario rows: **{len(rows)}**. Unique physical circuits: **{summary['unique_physical_circuits']}**. "
        "Nominal capacitor points shared between tolerance scenarios are simulated once and reused.", "",
        "**Incomplete smoke test**" if incomplete else "Full configured sweep completed.", "",
        "C1 and C2 each have nominal value 10 nF. Primary tolerance: ±10%; comparisons: ±1%, ±5%. "
        "Each capacitor independently takes its lower limit, nominal value, and upper limit. "
        "The 3×3 grid is a deterministic sampled grid, not a statistical distribution or manufacturing yield estimate.", "",
        "## Closest nominal resistor pairs", "",
        "These minimize nominal simulated frequency error among settled independently swept R1/R2 pairs in this finite search. "
        "They are not guaranteed to meet an unspecified lab acceptance limit or all capacitance values.", "",
        "| Target (Hz) | R1 series (Ω) | R2 shunt (Ω) | Simulated (Hz) | Error (%) | Vpp (V) | THD 2–10 (%) |",
        "|---:|---:|---:|---:|---:|---:|---:|"]
    for target in cfg["targets_hz"]:
        best = summary["oscillators"][str(target)]["best_nominal_any_pair"]
        if best:
            report.append(f"| {target} | {best['R1_ohm']:g} | {best['R2_ohm']:g} | {best['simulated_frequency_hz']:.4f} | "
                f"{best['simulated_abs_error_percent']:.4f} | {best['steady_state_vpp_v']:.4f} | {best['thd_2_to_10_percent']:.4f} |")
    report += ["", "Exact parts are stored in `selected_nominal_values.json` and implemented in `circuits/selected_*Hz`. "
        "The 1209 Hz choice has unequal R1/R2; the generalized network equations apply. "
        "Balanced alternatives are retained in `summary.json` and the nominal candidate tables.", "",
        "## Oscillation status", "", "| Target (Hz) | Status | Scenario rows |", "|---:|---|---:|"]
    for target in cfg["targets_hz"]:
        for status, count in summary["oscillators"][str(target)]["status_counts"].items():
            report.append(f"| {target} | {status} | {count} |")
    report += ["", "## Primary ±10% capacitor results for the closest nominal candidates", "",
        "Frequencies below include settled sample points only. A nonsettling point remains explicitly identified "
        "in the lookup CSV; omitted frequencies must not be read as a successful result.", "",
        "| Target (Hz) | Settled points / 9 | Min Hz | Max Hz | Worst sampled error (%) |",
        "|---:|---:|---:|---:|---:|"]
    for target in cfg["targets_hz"]:
        best = summary["oscillators"][str(target)]["best_nominal_any_pair"]
        if best:
            matches = [r for r in comparisons if r["target_hz"] == target and r["cap_tolerance_percent"] == 10
                       and r["R1_ohm"] == best["R1_ohm"] and r["R2_ohm"] == best["R2_ohm"]]
            for r in matches:
                report.append(f"| {target} | {r['settled_grid_points']} / {r['simulated_grid_points']} | "
                    f"{r['minimum_frequency_hz']:.3f} | {r['maximum_frequency_hz']:.3f} | {r['worst_sampled_abs_error_percent']:.3f} |")
    report += ["", "For matched capacitors shifting together, ideal frequency scales as 1/C: "
        "a ±10% capacitance range alone gives −9.09% to +11.11% frequency shift at fixed R. "
        "Accurate nominal resistors therefore do not eliminate capacitor tolerance. "
        "See `tolerance_comparison.csv` for the separate ±1%, ±5%, and ±10% cases.", "",
        "## Numerical verification", "", "Each selected closest nominal candidate was rerun with the maximum timestep halved. "
        "The measured changes are recorded in `timestep_convergence.csv`; these are numerical diagnostics, not lab acceptance limits.", ""]
    for check in checks:
        if "frequency_change_percent" in check:
            report.append(f"- {check['target_hz']} Hz candidate: frequency changes by {check['frequency_change_percent']:.6f}% when the maximum timestep is halved.")
    if not no_plots:
        report += ["", "## Waveforms and spectra", ""]
        for target in cfg["targets_hz"]:
            report += [f"![{target} Hz waveform and FFT](figures/oscillator_{target}Hz.png)", "",
                       f"![{target} Hz resistor sweep](figures/resistor_sweep_{target}Hz.png)", "",
                       f"![{target} Hz capacitor sweep](figures/capacitor_sweep_{target}Hz.png)", ""]
    (results/"RESULTS.md").write_text("\n".join(report)+"\n")
    # Offline HTML entry point; source report and CSV files remain independently usable.
    parts = ["<!doctype html><html><head><meta charset='utf-8'><title>Wien oscillator results</title>",
        "<style>body{font:16px system-ui;max-width:1050px;margin:40px auto;padding:0 24px;color:#172536}"
        "img{max-width:100%;height:auto}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:9px}"
        "pre{white-space:pre-wrap}a{color:#135f94}</style></head><body>",
        "<h1>Independent Wien bridge oscillator results</h1>",
        f"<p>{len(rows)} scenario rows; {summary['unique_physical_circuits']} unique physical circuits. "
        "Supplied TL074 model, ±12 V supplies, 10 nF capacitors.</p>",
        "<p>Primary capacitor tolerance ±10%; comparisons ±1% and ±5%. "
        "Both Wien resistors and both capacitor deviations vary independently.</p>",
        "<p>Open <a href='RESULTS.md'>RESULTS.md</a> for interpretation and limitations. "
        "The <a href='tolerance_comparison.csv'>tolerance table</a> compares all resistor pairs.</p>"]
    for target in cfg["targets_hz"]:
        info = summary["oscillators"][str(target)]
        parts += [f"<h2>{target} Hz oscillator</h2>",
            f"<p><a href='simulation_lookup_{target}Hz.csv'>Full simulation lookup CSV</a> · "
            f"<a href='nominal_candidates_{target}Hz.csv'>Nominal candidate ranking</a></p>",
            "<pre>"+html.escape(json.dumps(info, indent=2))+"</pre>"]
        if not no_plots:
            parts += [f"<img src='figures/oscillator_{target}Hz.png' alt='Startup, waveform, FFT'>",
                      f"<img src='figures/resistor_sweep_{target}Hz.png' alt='R1 and R2 sweep'>",
                      f"<img src='figures/capacitor_sweep_{target}Hz.png' alt='C1 and C2 tolerance sweep'>"]
    parts.append("</body></html>")
    (results/"index.html").write_text("\n".join(parts))
