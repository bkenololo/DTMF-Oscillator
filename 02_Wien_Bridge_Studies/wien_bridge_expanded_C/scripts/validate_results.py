#!/usr/bin/env python3
"""Validate broad/refined coverage, physical equations, models and SPICE evidence."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT))
import wien


def validate(results):
    cfg=json.loads((results/'config_used.json').read_text())
    if cfg.get('resistor_grid_mode')=='fine_E24_series_combinations':
        from run_refinement import refinement_candidates
        wien.resistor_candidates=refinement_candidates
    expected=wien.make_rows(cfg)
    provenance=json.loads((ROOT/'models/provenance.json').read_text())
    for file,key in [('TL074.301','original_sha256'),('TL074_ngspice.lib','normalized_sha256'),
                     ('1N4148.lib','diode_model_sha256')]:
        assert hashlib.sha256((ROOT/'models'/file).read_bytes()).hexdigest()==provenance[key]
    report={'models_match_recorded_hashes':True,'oscillators':{}}
    all_ids=set()
    for target in cfg['targets_hz']:
        with (results/f'simulation_lookup_{target}Hz.csv').open() as file:
            rows=list(csv.DictReader(file))
        expected_target=[r for r in expected if r['target_hz']==target]
        assert len(rows)==len(expected_target)
        counts=Counter((round(float(r['C_nominal_f'])*1e9,9),float(r['cap_tolerance_percent'])) for r in rows)
        expected_counts=Counter((round(r['C_nominal_f']*1e9,9),r['cap_tolerance_percent']) for r in expected_target)
        assert counts==expected_counts
        ids={r['case_id'] for r in rows}
        assert ids=={r['case_id'] for r in expected_target}
        all_ids |= ids
        evidence={}
        for row in rows:
            r1,r2,c1,c2=(float(row[k]) for k in ('R1_ohm','R2_ohm','C1_f','C2_f'))
            assert math.isclose(1/(2*math.pi*math.sqrt(r1*r2*c1*c2)),float(row['theory_zero_phase_hz']),rel_tol=1e-12)
            assert row['simulation_status']=='ok'
            if row['oscillation_status']=='settled_oscillation':
                measured=float(row['simulated_frequency_hz'])
                assert measured>0 and float(row['thd_2_to_10_percent'])>=0
                assert math.isclose(float(row['simulated_abs_error_percent']),100*abs(measured-target)/target,
                                    rel_tol=1e-10,abs_tol=1e-10)
            if row['case_id'] not in evidence:
                folder=results/'cases'/row['case_id']
                assert (folder/'circuit.cir').is_file() and (folder/'ngspice.log').is_file()
                evidence[row['case_id']]=json.loads((folder/'metrics.json').read_text())
                assert evidence[row['case_id']]['simulation_status']=='ok'
            if row['simulated_frequency_hz']:
                assert float(row['simulated_frequency_hz'])==evidence[row['case_id']]['simulated_frequency_hz']
        report['oscillators'][str(target)]={'scenario_rows':len(rows),'unique_physical_circuits':len(ids),
            'rows_per_C_and_tolerance':sorted(set(counts.values())),
            'nominal_capacitance_values_nF':sorted(set(k[0] for k in counts)),
            'simulator_failures':0,'statuses':dict(Counter(r['oscillation_status'] for r in rows))}
    summary=json.loads((results/'summary.json').read_text())
    assert summary['incomplete'] is False
    assert len(all_ids)==summary['unique_physical_circuits']
    for check in summary['timestep_checks']:
        assert check['simulation_status']=='ok'
        assert check['original_status']==check['refined_status']=='settled_oscillation'
    report['unique_physical_circuits']=len(all_ids)
    report['total_scenario_rows']=sum(v['scenario_rows'] for v in report['oscillators'].values())
    report['numerical_checks']=summary['timestep_checks']
    (results/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f"Validated {report['total_scenario_rows']} rows and {len(all_ids)} actual circuit runs: {results}")


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=ROOT/'results')
    validate(parser.parse_args().results.resolve())
