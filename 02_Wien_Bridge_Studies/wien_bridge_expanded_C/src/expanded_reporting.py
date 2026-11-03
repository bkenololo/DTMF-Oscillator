"""Reports for multiple standard nominal capacitors and their independent tolerances."""
from collections import Counter
import html
import json
import math
from pathlib import Path
import subprocess

import numpy as np

SELECTED_FIELDS = ("case_id", "target_hz", "C_nominal_f", "C_nominal_nF", "C_nominal_value_series",
    "R1_ohm", "R2_ohm", "R1_parts_ohm", "R2_parts_ohm", "resistor_count",
    "theory_zero_phase_hz", "simulated_frequency_hz", "simulated_abs_error_percent",
    "steady_state_vpp_v", "thd_2_to_10_percent", "settling_time_s", "oscillation_status")


def compact(row):
    return {k: row.get(k) for k in SELECTED_FIELDS} if row else None


def nominal_ranking(rows):
    """Rank only components at their nominal values, never tolerance-assisted matches."""
    seen = {r["case_id"]: r for r in rows if r["capacitors_nominal"]}
    return sorted(seen.values(), key=lambda r: (
        r.get("oscillation_status") != "settled_oscillation",
        r.get("simulated_abs_error_percent") if r.get("simulated_abs_error_percent") is not None else math.inf,
        r["resistor_count"], r["C_nominal_f"], r["R1_ohm"], r["R2_ohm"]))


def tolerance_ranking(rows, cfg):
    groups = {}
    for r in rows:
        # Nominal C is essential: equal physical capacitances can belong to different scenarios.
        key = tuple(r[k] for k in ("target_hz", "C_nominal_f", "cap_tolerance_percent", "R1_ohm", "R2_ohm"))
        groups.setdefault(key, []).append(r)
    result = []
    expected = len(cfg["capacitance_sweep_levels"])**2
    for (target, cap, tol, r1, r2), cases in groups.items():
        stable = [r for r in cases if r.get("oscillation_status") == "settled_oscillation"]
        result.append(dict(target_hz=target, C_nominal_f=cap, C_nominal_nF=round(cap*1e9, 9),
            cap_tolerance_percent=tol, R1_ohm=r1, R2_ohm=r2,
            simulated_grid_points=len(cases), expected_grid_points=expected,
            settled_grid_points=len(stable), all_sampled_points_settled=(len(stable) == expected),
            minimum_frequency_hz=min((r["simulated_frequency_hz"] for r in stable), default=None),
            maximum_frequency_hz=max((r["simulated_frequency_hz"] for r in stable), default=None),
            worst_sampled_abs_error_percent=max((r["simulated_abs_error_percent"] for r in stable), default=None),
            worst_sampled_thd_percent=max((r["thd_2_to_10_percent"] for r in stable), default=None)))
    result.sort(key=lambda r: (r["target_hz"], r["C_nominal_f"], r["cap_tolerance_percent"],
        not r["all_sampled_points_settled"], -r["settled_grid_points"],
        r["worst_sampled_abs_error_percent"] if r["worst_sampled_abs_error_percent"] is not None else math.inf))
    return result


def charts(rows, summary, cfg, results):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    figures = results/"figures"
    figures.mkdir(exist_ok=True)
    for target in cfg["targets_hz"]:
        info = summary["oscillators"][str(target)]
        ranked = nominal_ranking([r for r in rows if r["target_hz"] == target])
        best = info["best_nominal_any_pair"]
        # Show every standard nominal C, rather than a heatmap that silently merges C values.
        fig, axes = plt.subplots(2, 1, figsize=(10, 7), constrained_layout=True)
        for r in ranked:
            if r.get("oscillation_status") == "settled_oscillation":
                axes[0].scatter(r["C_nominal_nF"], r["simulated_signed_error_percent"],
                                s=18, color="#83a8c5", alpha=0.65)
        best_by_c = info["best_by_nominal_capacitance"]
        chosen = [r for r in best_by_c if r]
        axes[0].plot([r["C_nominal_nF"] for r in chosen],
            [100*(r["simulated_frequency_hz"]-target)/target for r in chosen],
            "o-", color="#a63224", label="Closest settled nominal pair at each C")
        axes[0].axhline(0, color="black", lw=0.8)
        axes[0].set(ylabel="Frequency error (%)", title=f"{target} Hz: nominal capacitor alternatives")
        axes[0].legend(fontsize=9)
        axes[1].plot([r["C_nominal_nF"] for r in chosen],
            [r["simulated_abs_error_percent"] for r in chosen], "o-", color="#135f94")
        axes[1].set(xlabel="Common nominal C1 = C2 (nF)", ylabel="Smallest nominal error (%)",
                    title="Each point uses a separately selected R1/R2 pair; capacitors are at nominal values")
        for ax in axes:
            ax.set_xticks([round(c*1e9, 9) for c in cfg["capacitance_nominal_values_f"]])
            ax.grid(axis="y", alpha=0.2)
        fig.savefig(figures/f"nominal_capacitor_comparison_{target}Hz.png", dpi=150)
        plt.close(fig)
        if not best:
            continue
        trace = np.load(results/"representatives"/f"{target}Hz"/"trace.npz")
        t, v = trace["time_s"], trace["output_v"]
        fig, axes = plt.subplots(3, 1, figsize=(10, 8), constrained_layout=True)
        axes[0].plot(t[::10]*1000, v[::10], lw=0.6, color="#135f94")
        axes[0].set(xlabel="Time (ms)", ylabel="Output (V)", title="Startup and settling")
        tail = t >= t[-1]-0.012
        axes[1].plot((t[tail]-t[-1]+0.012)*1000, v[tail], color="#135f94")
        axes[1].set(xlabel="Time within final 12 ms", ylabel="Output (V)", title="Settled waveform")
        uniform = np.arange(t[-1]-cfg["analysis_window_s"], t[-1], cfg["maximum_time_step_s"])
        signal = np.interp(uniform, t, v)
        signal -= np.mean(signal)
        window = np.hanning(len(signal))
        spectrum = 2*np.abs(np.fft.rfft(signal*window))/window.sum()
        f = np.fft.rfftfreq(len(signal), cfg["maximum_time_step_s"])
        db = 20*np.log10(np.maximum(spectrum, 1e-12)/np.max(spectrum))
        axes[2].plot(f, db, color="#135f94", lw=0.9)
        axes[2].axvline(target, color="#a63224", ls="--", lw=0.8, label=f"Target {target} Hz")
        axes[2].set(xlabel="Frequency (Hz)", ylabel="Magnitude (dBc)", xlim=(0, 10.5*target),
                    ylim=(-100, 5), title=f"Hann-window FFT; bin spacing {1/cfg['analysis_window_s']:g} Hz")
        axes[2].legend()
        fig.suptitle(f"{target} Hz: C1 = C2 = {best['C_nominal_nF']:g} nF, R1 = {best['R1_ohm']/1000:g} kΩ, R2 = {best['R2_ohm']/1000:g} kΩ\n"
            f"{best['simulated_frequency_hz']:.3f} Hz; {best['steady_state_vpp_v']:.3f} Vpp; THD (2–10) {best['thd_2_to_10_percent']:.3f}%")
        fig.savefig(figures/f"oscillator_{target}Hz.png", dpi=150)
        plt.close(fig)
        # For the selected nominal component set, retain the earlier 3x3 tolerance plot.
        fig, axes = plt.subplots(1, len(cfg["capacitance_tolerances_fraction"]), figsize=(13, 5), squeeze=False)
        fig.subplots_adjust(left=0.055, right=0.88, bottom=0.17, top=0.76, wspace=0.30)
        color = plt.get_cmap("RdBu_r").copy()
        color.set_bad("#dddddd")
        for ax, tolerance in zip(axes[0], cfg["capacitance_tolerances_fraction"]):
            samples = [r for r in rows if r["target_hz"] == target and r["C_nominal_f"] == best["C_nominal_f"]
                and abs(r["cap_tolerance_percent"]-100*tolerance) < 1e-9
                and r["R1_ohm"] == best["R1_ohm"] and r["R2_ohm"] == best["R2_ohm"]]
            offsets = sorted(set(r["C1_offset_percent"] for r in samples))
            matrix, freqs = np.full((3, 3), np.nan), np.full((3, 3), np.nan)
            for r in samples:
                if r.get("oscillation_status") == "settled_oscillation":
                    y, x = offsets.index(r["C2_offset_percent"]), offsets.index(r["C1_offset_percent"])
                    matrix[y, x] = r["simulated_signed_error_percent"]
                    freqs[y, x] = r["simulated_frequency_hz"]
            im = ax.imshow(matrix, origin="lower", cmap=color, vmin=-13, vmax=13)
            labels = [f"{best['C_nominal_nF']*(1+x/100):g}" for x in offsets]
            ax.set_xticks(range(3), labels)
            ax.set_yticks(range(3), labels)
            ax.set(xlabel="Actual C1 (nF)", ylabel="Actual C2 (nF)", title=f"±{100*tolerance:g}% tolerance")
            for y, x in np.ndindex(matrix.shape):
                ax.text(x, y, f"{freqs[y,x]:.1f} Hz\n{matrix[y,x]:+.2f}%" if np.isfinite(matrix[y,x]) else "No settled\noscillation",
                    ha="center", va="center", fontsize=8,
                    color="white" if np.isfinite(matrix[y,x]) and abs(matrix[y,x])>8 else "black")
        cax = fig.add_axes([0.91, 0.18, 0.016, 0.57])
        fig.colorbar(im, cax=cax, label="Simulated frequency error (%)")
        fig.suptitle(f"{target} Hz: tolerance around selected standard nominal C = {best['C_nominal_nF']:g} nF\n"
            f"R1 = {best['R1_ohm']/1000:g} kΩ, R2 = {best['R2_ohm']/1000:g} kΩ")
        fig.savefig(figures/f"capacitor_tolerance_{target}Hz.png", dpi=150)
        plt.close(fig)


def make_report(rows, cfg, results, executable, incomplete=False, no_plots=False):
    from wien import ROOT, write_csv, write_netlist
    from reporting import inspect_representative
    summary = dict(scope="Expanded common nominal C; two independent oscillators; no summing stage",
        incomplete=incomplete, scenario_rows=len(rows),
        unique_physical_circuits=len({r["case_id"] for r in rows}),
        capacitance_nominal_values_nF=[round(c*1e9, 9) for c in cfg["capacitance_nominal_values_f"]],
        primary_cap_tolerance_percent=100*cfg["primary_capacitance_tolerance_fraction"],
        ngspice_version=subprocess.check_output([executable, "--version"], text=True).strip(), oscillators={})
    comparisons = tolerance_ranking(rows, cfg)
    write_csv(results/"tolerance_comparison.csv", comparisons)
    checks = []
    previous = json.loads((ROOT/"reference/previous_summary.json").read_text())
    for target in cfg["targets_hz"]:
        subset = [r for r in rows if r["target_hz"] == target]
        ranking = nominal_ranking(subset)
        write_csv(results/f"nominal_candidates_{target}Hz.csv", ranking)
        stable = [r for r in ranking if r.get("oscillation_status") == "settled_oscillation"]
        balanced = [r for r in stable if r["R1_ohm"] == r["R2_ohm"]]
        by_c = []
        for cap in cfg["capacitance_nominal_values_f"]:
            at_c = [r for r in stable if r["C_nominal_f"] == cap]
            by_c.append(compact(at_c[0]) if at_c else None)
        write_csv(results/f"best_per_nominal_C_{target}Hz.csv", [r for r in by_c if r])
        info = dict(scenario_rows=len(subset), unique_physical_circuits=len({r["case_id"] for r in subset}),
            status_counts=dict(Counter(r.get("oscillation_status") for r in subset)),
            simulator_failures=sum(r.get("simulation_status") != "ok" for r in subset),
            best_nominal_any_pair=compact(stable[0]) if stable else None,
            best_balanced_nominal=compact(balanced[0]) if balanced else None,
            best_by_nominal_capacitance=by_c,
            previous_10nF_best=previous["oscillators"][str(target)]["best_nominal_any_pair"])
        summary["oscillators"][str(target)] = info
        if stable:
            selected = stable[0]
            check = inspect_representative(selected, cfg, results, executable)
            check["C_nominal_f"] = selected["C_nominal_f"]
            checks.append(check)
            write_netlist(selected, cfg, results.parent/"circuits"/f"selected_{target}Hz")
            # Each nominal-C winner has an inspectable, standalone netlist too.
            for winner in by_c:
                if winner:
                    source = next(r for r in stable if r["case_id"] == winner["case_id"])
                    write_netlist(source, cfg, results.parent/"circuits"/f"{target}Hz"/f"C_{winner['C_nominal_nF']:g}nF")
    write_csv(results/"timestep_convergence.csv", checks)
    summary["timestep_checks"] = checks
    (results/"summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n")
    (results/"selected_nominal_values.json").write_text(json.dumps({
        "selection_rule": "Minimum nominal simulated frequency error among settled candidates in this finite C/R grid; no tolerance offsets used for selection.",
        "primary_cap_tolerance_percent": 100*cfg["primary_capacitance_tolerance_fraction"],
        "oscillators": {str(t): summary["oscillators"][str(t)]["best_nominal_any_pair"] for t in cfg["targets_hz"]}
    }, indent=2)+"\n")
    if not no_plots:
        charts(rows, summary, cfg, results)
    lines = ["# Expanded nominal capacitor sweep", "",
        "The original TL074 model, diode models, circuit, supplies, load condition, startup seed, "
        "transient duration, and measurement method are retained. Only the nominal-capacitor search "
        "is expanded; the original resistor choices are retained.", "",
        f"**{len(rows):,} scenario rows; {summary['unique_physical_circuits']:,} unique physical circuits.** "
        +( "This is an incomplete smoke test." if incomplete else "The full configured sweep completed."), "",
        "Nominal C values (nF): "+", ".join(f"{x:g}" for x in summary["capacitance_nominal_values_nF"])+". "
        "Each is an E24 value; E12 membership is identified separately in the tables. "
        "C1 and C2 share that nominal value, then independently take −tolerance, nominal, and +tolerance "
        "for each of ±1%, ±5%, and ±10%.", "",
        "## Closest nominal components", "",
        "Selection uses both capacitors at nominal value. Tolerance-assisted frequency matches are "
        "retained in the full tables but are not labeled better nominal designs. "
        "The closest frequency is not automatically the lowest-distortion design; THD is reported explicitly.", "",
        "| Target Hz | C1=C2 nF | R1 series Ω | R2 shunt Ω | Simulated Hz | Error % | THD 2–10 % | Previous 10 nF Hz |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for target in cfg["targets_hz"]:
        info = summary["oscillators"][str(target)]
        r = info["best_nominal_any_pair"]
        if r:
            lines.append(f"| {target} | {r['C_nominal_nF']:g} | {r['R1_ohm']:g} | {r['R2_ohm']:g} | "
                f"{r['simulated_frequency_hz']:.4f} | {r['simulated_abs_error_percent']:.4f} | "
                f"{r['thd_2_to_10_percent']:.3f} | {info['previous_10nF_best']['simulated_frequency_hz']:.4f} |")
    lines += ["", "The resistor series parts and nominal capacitor specification are saved in "
        "`selected_nominal_values.json`; `circuits/selected_*Hz/circuit.cir` implements each selection. "
        "Other C choices and balanced R1=R2 alternatives remain in the ranking tables and `summary.json`.", "",
        "## Best settled nominal pair at every standard capacitor value", "",
        "| Target Hz | Nominal C nF | R1 Ω | R2 Ω | Simulated Hz | Error % | THD % |",
        "|---:|---:|---:|---:|---:|---:|---:|"]
    for target in cfg["targets_hz"]:
        for r in summary["oscillators"][str(target)]["best_by_nominal_capacitance"]:
            if r:
                lines.append(f"| {target} | {r['C_nominal_nF']:g} | {r['R1_ohm']:g} | {r['R2_ohm']:g} | "
                    f"{r['simulated_frequency_hz']:.4f} | {r['simulated_abs_error_percent']:.4f} | {r['thd_2_to_10_percent']:.3f} |")
    lines += ["", "## Primary ±10% tolerance grid for the selected nominal components", "",
        "These ranges include only settled points. The table explicitly counts how many of the nine "
        "sampled points settled; it is not a probability, yield estimate, or continuous-tolerance guarantee.", "",
        "| Target Hz | Settled / sampled | Minimum Hz | Maximum Hz | Worst error % |",
        "|---:|---:|---:|---:|---:|"]
    for target in cfg["targets_hz"]:
        best = summary["oscillators"][str(target)]["best_nominal_any_pair"]
        if best:
            for r in comparisons:
                if (r["target_hz"],r["C_nominal_f"],r["cap_tolerance_percent"],r["R1_ohm"],r["R2_ohm"]) == (
                    target,best["C_nominal_f"],10,best["R1_ohm"],best["R2_ohm"]):
                    lines.append(f"| {target} | {r['settled_grid_points']} / {r['simulated_grid_points']} | "
                        f"{r['minimum_frequency_hz']:.3f} | {r['maximum_frequency_hz']:.3f} | {r['worst_sampled_abs_error_percent']:.3f} |")
    lines += ["", "## Numerical checks and limits", "",
        "The selected nominal candidates were rerun with the maximum timestep halved from 5 to 2.5 µs. "
        "Their changes are in `timestep_convergence.csv`. The nominal tables use the common 5 µs setting "
        "for comparability; extra decimal places do not imply corresponding physical accuracy.", ""]
    for check in checks:
        if "frequency_change_percent" in check:
            lines.append(f"- {check['target_hz']} Hz: frequency changes {check['frequency_change_percent']:.6f}% with half the maximum timestep.")
    lines += ["", "The tolerance grid is deterministic. Capacitor parasitics, manufacturing distributions, "
        "resistor manufacturing tolerance, temperature/supply variation, and summing-amplifier loading "
        "are outside this stage. Nominal optimization does not eliminate capacitor tolerance; physical "
        "parts may still need measurement and trimming. No lab pass/fail limits are assumed.", ""]
    if not no_plots:
        for target in cfg["targets_hz"]:
            lines += [f"## {target} Hz figures", "",
                f"![Nominal capacitor alternatives](figures/nominal_capacitor_comparison_{target}Hz.png)", "",
                f"![Selected waveform and spectrum](figures/oscillator_{target}Hz.png)", "",
                f"![Selected capacitor tolerance](figures/capacitor_tolerance_{target}Hz.png)", ""]
    (results/"RESULTS.md").write_text("\n".join(lines)+"\n")
    pieces = ["<!doctype html><html><head><meta charset='utf-8'><title>Expanded Wien capacitor sweep</title>",
        "<style>body{font:16px system-ui;max-width:1150px;margin:36px auto;padding:0 24px;color:#172536}"
        "img{max-width:100%;height:auto}table{border-collapse:collapse}th,td{border:1px solid #bbb;padding:8px;text-align:right}"
        "pre{white-space:pre-wrap}a{color:#135f94}</style></head><body>",
        "<h1>Expanded nominal capacitor sweep</h1>",
        f"<p>{len(rows):,} scenario rows; {summary['unique_physical_circuits']:,} unique physical circuits. "
        "The original circuit and resistor grids are retained.</p>",
        "<p><a href='RESULTS.md'>Full interpretation</a> · <a href='tolerance_comparison.csv'>Tolerance comparison CSV</a></p>",
        "<p>Selections use nominal capacitor values. ±1%, ±5%, and ±10% tolerance points are separate tests.</p>"]
    for target in cfg["targets_hz"]:
        info = summary["oscillators"][str(target)]
        pieces += [f"<h2>{target} Hz oscillator</h2>",
            f"<p><a href='simulation_lookup_{target}Hz.csv'>All simulation rows</a> · "
            f"<a href='nominal_candidates_{target}Hz.csv'>Nominal ranking</a> · "
            f"<a href='best_per_nominal_C_{target}Hz.csv'>Best pair at each nominal C</a></p>",
            "<table><tr><th>C nF</th><th>R1 Ω</th><th>R2 Ω</th><th>Simulated Hz</th><th>Error %</th><th>THD %</th></tr>"]
        for r in info["best_by_nominal_capacitance"]:
            if r:
                pieces.append(f"<tr><td>{r['C_nominal_nF']:g}</td><td>{r['R1_ohm']:g}</td><td>{r['R2_ohm']:g}</td>"
                    f"<td>{r['simulated_frequency_hz']:.4f}</td><td>{r['simulated_abs_error_percent']:.4f}</td>"
                    f"<td>{r['thd_2_to_10_percent']:.3f}</td></tr>")
        pieces.append("</table><p>Closest nominal selection:</p><pre>"+html.escape(json.dumps(info["best_nominal_any_pair"],indent=2))+"</pre>")
        if not no_plots:
            pieces += [f"<img src='figures/nominal_capacitor_comparison_{target}Hz.png' alt='Nominal capacitor alternatives'>",
                f"<img src='figures/oscillator_{target}Hz.png' alt='Selected waveform and FFT'>",
                f"<img src='figures/capacitor_tolerance_{target}Hz.png' alt='Tolerance around selected capacitor'>"]
    pieces.append("</body></html>")
    (results/"index.html").write_text("\n".join(pieces))
