#!/usr/bin/env python3
"""Combine the two completed sweeps, preserving their distinct search scopes."""
import csv
import html
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from wien import write_netlist


def main():
    stages={
        'broad_C':(ROOT/'results','Broad nominal C, original R grid'),
        'fine_R':(ROOT/'refinement/results','Fine E24 series resistors, nominal C=10 nF')}
    previous=json.loads((ROOT/'reference/previous_summary.json').read_text())
    summaries={}
    configs={}
    for name,(folder,label) in stages.items():
        summaries[name]=json.loads((folder/'summary.json').read_text())
        assert not summaries[name]['incomplete'],f'{name} is incomplete'
        assert all(v['simulator_failures']==0 for v in summaries[name]['oscillators'].values())
        configs[name]=json.loads((folder/'config_used.json').read_text())
    selected={}
    comparison=[]
    verified_file=ROOT/'verification/results/selected_nominal_values.json'
    verified=json.loads(verified_file.read_text()) if verified_file.exists() else None
    if verified:
        assert verified['selected_tolerance_comparison_rows']==6, 'Rerun verify_finalists.py after both full tolerance sweeps finish'
    for target in configs['broad_C']['targets_hz']:
        old=previous['oscillators'][str(target)]['best_nominal_any_pair']
        comparison.append(dict(target_hz=target,stage='previous_10nF',C_nominal_nF=10,
            R1_ohm=old['R1_ohm'],R2_ohm=old['R2_ohm'],R1_parts_ohm=old['R1_parts_ohm'],
            R2_parts_ohm=old['R2_parts_ohm'],simulated_frequency_hz=old['simulated_frequency_hz'],
            simulated_abs_error_percent=old['simulated_abs_error_percent'],
            thd_2_to_10_percent=old['thd_2_to_10_percent']))
        candidates=[]
        for name,summary in summaries.items():
            row=dict(summary['oscillators'][str(target)]['best_nominal_any_pair'],source_stage=name)
            candidates.append(row)
            comparison.append(dict(target_hz=target,stage=name,**{k:row[k] for k in
                ('C_nominal_nF','R1_ohm','R2_ohm','R1_parts_ohm','R2_parts_ohm',
                 'simulated_frequency_hz','simulated_abs_error_percent','thd_2_to_10_percent')}))
        winner=min(candidates,key=lambda r:r['simulated_abs_error_percent'])
        if verified:
            winner=verified['oscillators'][str(target)]
        else:
            checks=summaries[winner['source_stage']]['timestep_checks']
            check=next(c for c in checks if c['target_hz']==target)
            winner['half_timestep_frequency_hz']=check['refined_frequency_hz']
            winner['numerical_frequency_change_percent']=check['frequency_change_percent']
        selected[str(target)]=winner
        netrow=dict(winner,C1_f=winner['C_nominal_f'],C2_f=winner['C_nominal_f'])
        netcfg=dict(configs[winner['source_stage']])
        if verified:netcfg['maximum_time_step_s']=winner['verification_maximum_timestep_s']
        write_netlist(netrow,netcfg,ROOT/'circuits'/f'recommended_{target}Hz')
    (ROOT/'selected_nominal_values.json').write_text(json.dumps({
        'selection_rule':verified['selection_rule'] if verified else 'Smallest nominal simulated frequency error among settled candidates in the two finite searches. THD is shown separately; no tolerance offsets used for selection.',
        'oscillators':selected},indent=2)+'\n')
    with (ROOT/'comparison.csv').open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=list(comparison[0]))
        writer.writeheader();writer.writerows(comparison)
    lines=['# Expanded Wien bridge sweep overview','',
        'The requested broad sweep varies standard nominal capacitors, then independently tests '
        'the ±1%, ±5%, and ±10% endpoints of both capacitors at every nominal value. '
        'The original resistor grids, circuit and simulation settings are retained.','',
        'A separately labelled fine-resistor search improves nominal frequency matching using '
        'neighboring E24 values in the existing series combinations. It is not conflated with '
        'the unchanged-resistor broad capacitor search.','',
        '| Target Hz | Search | C1=C2 nF | R1 Ω | R2 Ω | Simulated Hz | Error % | THD 2–10 % |',
        '|---:|---|---:|---:|---:|---:|---:|---:|']
    for row in comparison:
        lines.append(f"| {row['target_hz']} | {row['stage']} | {row['C_nominal_nF']:g} | "
            f"{row['R1_ohm']:g} | {row['R2_ohm']:g} | {row['simulated_frequency_hz']:.4f} | "
            f"{row['simulated_abs_error_percent']:.4f} | {row['thd_2_to_10_percent']:.3f} |")
    lines += ['',
        '**Result:** changing only nominal C within the retained R grid did not improve the '
        '770 Hz match. The finer resistor combinations improve it while retaining nominal 10 nF. '
        'For 1209 Hz, the broad sweep provides an 11 nF option with lower distortion; '
        'the fine-resistor sweep provides a closer nominal frequency at 10 nF.','',
        'The comparison table above uses the common 5 µs grid setting. Finalists below '
        'are additionally compared at a finer common timestep when the verification results are present.','',
        '## Closest nominal frequency choices','']
    for target,row in selected.items():
        lines += [f"- **{target} Hz:** C1=C2={row['C_nominal_nF']:g} nF; "
            f"R1={row['R1_parts_ohm']} Ω; R2={row['R2_parts_ohm']} Ω. "
            f"Simulated {row['simulated_frequency_hz']:.4f} Hz at "
            f"{row.get('verification_maximum_timestep_s',5e-6)*1e6:g} µs maximum timestep; "
            f"{row['half_timestep_frequency_hz']:.4f} Hz at half that timestep."]
    lines += ['',
        'These are the closest nominal-frequency cases in the finite search, not universal optima. '
        'The smallest frequency error does not imply lowest distortion. Numerical timestep '
        'differences limit meaningful precision, and capacitor manufacturing tolerance still '
        'changes the hardware frequency. No lab pass/fail limits have been assumed.','',
        '## Data and source files','',
        '- Broad capacitor sweep: [report](results/RESULTS.md), [HTML](results/index.html).',
        '- Separate fine resistor sweep: [report](refinement/results/RESULTS.md), [HTML](refinement/results/index.html).',
        '- Each stage includes all rows, nominal rankings, best pair at each C, tolerance grids, '
        'case netlists/logs, traces and numerical checks.',
        '- Final nominal components: `selected_nominal_values.json`.',
        '- Final circuit files: `circuits/recommended_770Hz/circuit.cir` and '
        '`circuits/recommended_1209Hz/circuit.cir`.',
        '- Running instructions and assumptions: `README.md`.','']
    (ROOT/'SUMMARY.md').write_text('\n'.join(lines))
    page=['<!doctype html><html><head><meta charset="utf-8"><title>Expanded Wien bridge sweep</title>',
        '<style>body{font:16px system-ui;max-width:1150px;margin:36px auto;padding:0 24px;color:#172536}'
        'table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:9px;text-align:right}'
        'img{max-width:100%;height:auto}a{color:#135f94}</style></head><body>',
        '<h1>Expanded Wien bridge sweep</h1>',
        '<p>Nine standard nominal C values: 6.8, 7.5, 8.2, 9.1, 10, 11, 12, 13, 15 nF. '
        'Independent ±1%, ±5%, ±10% capacitor deviations at each nominal value.</p>',
        '<p><a href="results/index.html">Requested broad capacitor sweep</a> · '
        '<a href="refinement/results/index.html">Separate fine resistor sweep</a> · '
        '<a href="SUMMARY.md">Interpretation</a> · <a href="README.md">Instructions</a></p>',
        '<table><tr><th>Target Hz</th><th>Search</th><th>C nF</th><th>R1 Ω</th><th>R2 Ω</th>'
        '<th>Simulated Hz</th><th>Error %</th><th>THD %</th></tr>']
    for r in comparison:
        page.append(f"<tr><td>{r['target_hz']}</td><td>{html.escape(r['stage'])}</td><td>{r['C_nominal_nF']:g}</td>"
            f"<td>{r['R1_ohm']:g}</td><td>{r['R2_ohm']:g}</td><td>{r['simulated_frequency_hz']:.4f}</td>"
            f"<td>{r['simulated_abs_error_percent']:.4f}</td><td>{r['thd_2_to_10_percent']:.3f}</td></tr>")
    page += ['</table><p>The finer resistor search improves nominal frequency accuracy. '
        'The broad sweep separately shows other nominal capacitors and their distortion/tolerance trade-offs. '
        'See both detailed reports before choosing hardware values.</p>']
    for target,row in selected.items():
        prefix='results' if row['source_stage']=='broad_C' else 'refinement/results'
        page += [f'<h2>{target} Hz closest nominal case</h2>',
            f'<p><a href="circuits/recommended_{target}Hz/circuit.cir">SPICE netlist</a></p>']
        if verified:
            page += [f'<p>C={row["C_nominal_nF"]:g} nF; R1={row["R1_ohm"]:g} Ω; '
                f'R2={row["R2_ohm"]:g} Ω; verified frequency {row["simulated_frequency_hz"]:.4f} Hz.</p>',
                f'<img src="verification/results/figures/finalist_{target}Hz.png" alt="Finer-step verified waveform and FFT">']
        else:
            page += [f'<img src="{prefix}/figures/oscillator_{target}Hz.png" alt="Selected waveform and spectrum">',
                f'<img src="{prefix}/figures/capacitor_tolerance_{target}Hz.png" alt="Selected capacitor tolerance">']
    page.append('</body></html>')
    (ROOT/'START_HERE.html').write_text('\n'.join(page))
    print('Combined overview and nominal circuit selections saved in',ROOT)


if __name__=='__main__':
    main()
