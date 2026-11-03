#!/usr/bin/env python3
"""Run --nominal first; run all studies by default. Sources/models are local."""
from pathlib import Path
import argparse,concurrent.futures as futures,json,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from summing import base_parameters,grid_rows,identify,physical_columns,run_case,write_csv,write_netlist,discover_ngspice


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--nominal',action='store_true');parser.add_argument('--workers',type=int,default=8)
    args=parser.parse_args();cfg=json.loads((ROOT/'config.json').read_text());exe=discover_ngspice();results=ROOT/'results'
    nominal=base_parameters(cfg);m=run_case(nominal,cfg,exe,results,keep=True)
    assert m['simulation_status']=='ok',m
    (results/'nominal.json').write_text(json.dumps(dict(parameters=nominal,measurement=m),indent=2)+'\n')
    write_netlist(nominal,cfg,ROOT/'circuits/nominal')
    print('Nominal:',json.dumps(m),flush=True)
    if args.nominal:return
    rows=grid_rows(cfg);unique={r['case_id']:r['parameters'] for r in rows}
    print(f'{len(rows)} tolerance scenario rows; {len(unique)} unique tolerance circuits',flush=True)
    measured={}
    with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending={pool.submit(run_case,p,cfg,exe,results):cid for cid,p in unique.items()}
        for n,job in enumerate(futures.as_completed(pending),1):
            measured[pending[job]]=job.result()
            if n%40==0 or n==len(pending):print(f'{n}/{len(pending)} tolerance circuits complete',flush=True)
    joined=[dict({k:v for k,v in r.items() if k!='parameters'},**physical_columns(r['parameters']),**measured[r['case_id']]) for r in rows]
    write_csv(results/'tolerance_all.csv',joined)
    for study in sorted({r['study'] for r in rows}):write_csv(results/f'tolerance_{study}.csv',[r for r in joined if r['study']==study])
    failures=[r for r in joined if r['simulation_status']!='ok']
    assert not failures,failures[:3]
    checks=[]
    for label,p in [('nominal_half_timestep',base_parameters(cfg,cfg['maximum_time_step_s']/2)),
        ('scope_10Mohm',base_parameters(cfg,load=1e7)),('no_external_load',base_parameters(cfg,load=None)),
        ('load_10kohm_stress',base_parameters(cfg,load=1e4))]:
        check=run_case(p,cfg,exe,results);assert check['simulation_status']=='ok',check
        checks.append(dict(check=label,**physical_columns(p),**check))
    write_csv(results/'numerical_and_load_checks.csv',checks)
    half=checks[0]
    for band in ('low','high'):
        delta=100*abs(half[f'{band}_simulated_frequency_hz']-m[f'{band}_simulated_frequency_hz'])/half[f'{band}_simulated_frequency_hz']
        assert delta<.02,(band,delta)
    assert m['both_oscillators_settled'] and not m['output_near_supply_rail']
    assert abs(m['measured_gain_low_magnitude']-10/22)<.001
    assert abs(m['measured_gain_high_magnitude']-10/22)<.001
    print('Simulation grid and numerical/load checks complete.',flush=True)

if __name__=='__main__':main()
