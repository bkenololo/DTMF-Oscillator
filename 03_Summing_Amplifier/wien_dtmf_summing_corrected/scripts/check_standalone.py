#!/usr/bin/env python3
"""Verify the exact pinned components standalone and compare equal timesteps."""
from pathlib import Path
import csv,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import wien_reference as wien
from summing import base_parameters
cfg=json.loads((ROOT/'config.json').read_text());exe=wien.discover_ngspice()
pinned=json.loads((ROOT/'reference/user_selected_table.json').read_text())['oscillators']
records=[];selected={}
for band,target in [('low',770),('high',1209)]:
    legs=cfg['oscillator_parts_ohm'][band]
    for step in (5e-6,1.25e-6):
        local=dict(cfg,output_load_ohm=None,maximum_time_step_s=step)
        row=dict(target_hz=target,R1_ohm=sum(legs['R1']),R2_ohm=sum(legs['R2']),
            R1_parts_ohm=' + '.join(str(x) for x in legs['R1']),R2_parts_ohm=' + '.join(str(x) for x in legs['R2']),
            C1_f=1e-8,C2_f=1e-8,case_id=f'standalone_{target}_{step:g}')
        assert (row['R1_ohm'],row['R2_ohm'])==(pinned[str(target)]['R1_ohm'],pinned[str(target)]['R2_ohm'])
        m=wien.run_case(row,local,exe,ROOT/'reference/standalone_runs')
        assert m['simulation_status']=='ok' and m['oscillation_status']=='settled_oscillation',m
        if step==5e-6:assert abs(m['simulated_frequency_hz']-pinned[str(target)]['simulated_frequency_hz'])<1e-6
        else:selected[str(target)]=dict(row,**m,maximum_time_step_s=step,component_choice_basis='User-pinned resistor pair, not a new optimization')
        records.append(dict(target_hz=target,maximum_time_step_s=step,R1_ohm=row['R1_ohm'],R2_ohm=row['R2_ohm'],**m))
        print(target,step,m['simulated_frequency_hz'],flush=True)
wien.write_csv(ROOT/'results/standalone_checks.csv',records)
(ROOT/'reference/selected_nominal_values.json').write_text(json.dumps({'selection_rule':'Exact user-pinned components; standalone baseline measured at 1.25 us to match the combined nominal run. Original 5 us table is independently checked.','oscillators':selected},indent=2)+'\n')
if (ROOT/'results/tolerance_all.csv').exists():
    with (ROOT/'results/tolerance_all.csv').open() as f:grid=list(csv.DictReader(f))
    grid_nom=next(r for r in grid if r['all_nominal']=='True')
    fine=json.loads((ROOT/'results/nominal.json').read_text())['measurement'];comparisons=[]
    for row in records:
        band='low' if row['target_hz']==770 else 'high'
        source=grid_nom if row['maximum_time_step_s']==5e-6 else fine
        connected=float(source[f'{band}_simulated_frequency_hz'])
        comparisons.append(dict(target_hz=row['target_hz'],R1_ohm=row['R1_ohm'],R2_ohm=row['R2_ohm'],maximum_time_step_s=row['maximum_time_step_s'],
            standalone_frequency_hz=row['simulated_frequency_hz'],connected_frequency_hz=connected,
            frequency_shift_from_summer_loading_hz=connected-row['simulated_frequency_hz']))
    wien.write_csv(ROOT/'results/timestep_and_loading_comparison.csv',comparisons)
