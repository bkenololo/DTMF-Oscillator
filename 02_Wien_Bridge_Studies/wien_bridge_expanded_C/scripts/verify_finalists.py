#!/usr/bin/env python3
"""Compare five closest nominal candidates per target at a common finer timestep."""
import csv
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from wien import discover_ngspice, run_case, write_csv
from reporting import inspect_representative
from expanded_reporting import compact


def typed(value):
    if value=='':return None
    if value in ('True','False'):return value=='True'
    try:return float(value)
    except ValueError:return value


def read_csv(path):
    with path.open() as file:
        return [{k:typed(v) for k,v in r.items()} for r in csv.DictReader(file)]


def main():
    cfg=json.loads((ROOT/'results/config_used.json').read_text())
    cfg['maximum_time_step_s']=1.25e-6
    out=ROOT/'verification/results'
    out.mkdir(parents=True,exist_ok=True)
    (out/'config_used.json').write_text(json.dumps(cfg,indent=2)+'\n')
    executable=discover_ngspice()
    comparisons=[]
    selected={}
    tolerances=[]
    checks=[]
    for target in cfg['targets_hz']:
        candidates={}
        for stage,folder in [('broad_C',ROOT/'results'),('fine_R',ROOT/'refinement/results')]:
            for r in read_csv(folder/f'nominal_candidates_{target}Hz.csv'):
                if r['oscillation_status']=='settled_oscillation':
                    r.update(source_stage=stage,original_grid_frequency_hz=r['simulated_frequency_hz'],
                             original_grid_error_percent=r['simulated_abs_error_percent'])
                    candidates.setdefault(r['case_id'],r)
        closest=sorted(candidates.values(),key=lambda r:r['simulated_abs_error_percent'])[:5]
        refined=[]
        for r in closest:
            r['target_hz']=target
            measurement=run_case(r,cfg,executable,out)
            assert measurement['simulation_status']=='ok'
            combined=dict(r,**measurement)
            comparisons.append(combined)
            if measurement['oscillation_status']=='settled_oscillation':refined.append(combined)
        assert refined
        winner=min(refined,key=lambda r:r['simulated_abs_error_percent'])
        check=inspect_representative(winner,cfg,out,executable)
        checks.append(check)
        chosen=dict(compact(winner),source_stage=winner['source_stage'],
            original_grid_frequency_hz=winner['original_grid_frequency_hz'],
            verification_maximum_timestep_s=cfg['maximum_time_step_s'],
            half_timestep_frequency_hz=check['refined_frequency_hz'],
            numerical_frequency_change_percent=check['frequency_change_percent'])
        selected[str(target)]=chosen
        source=ROOT/('results' if winner['source_stage']=='broad_C' else 'refinement/results')
        tolerance_file=source/'tolerance_comparison.csv'
        for r in read_csv(tolerance_file) if tolerance_file.exists() else []:
            if (r['target_hz'],r['C_nominal_f'],r['R1_ohm'],r['R2_ohm']) == (
                target,winner['C_nominal_f'],winner['R1_ohm'],winner['R2_ohm']):tolerances.append(r)
        print(f"{target} Hz: finer-step selection {winner['simulated_frequency_hz']:.6f} Hz, "
              f"R1={winner['R1_ohm']:g}, R2={winner['R2_ohm']:g}, C={winner['C_nominal_nF']:g} nF",flush=True)
    write_csv(out/'candidate_comparison.csv',comparisons)
    write_csv(out/'selected_tolerance_comparison_at_original_5us.csv',tolerances)
    write_csv(out/'timestep_convergence.csv',checks)
    (out/'selected_nominal_values.json').write_text(json.dumps({
        'selection_rule':'Closest nominal frequency among the five closest 5 us-grid candidates per target, compared at a common 1.25 us timestep, then checked at 0.625 us. No tolerance offsets used.',
        'selected_tolerance_comparison_rows':len(tolerances),
        'oscillators':selected},indent=2)+'\n')
    plot_selected(selected,cfg,out)


def plot_selected(selected,cfg,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    folder=out/'figures';folder.mkdir(exist_ok=True)
    for target,row in selected.items():
        data=np.load(out/'representatives'/f'{target}Hz'/'trace.npz')
        t,v=data['time_s'],data['output_v']
        fig,axes=plt.subplots(2,1,figsize=(10,6),constrained_layout=True)
        tail=t>=t[-1]-0.012
        axes[0].plot((t[tail]-t[-1]+0.012)*1000,v[tail])
        axes[0].set(xlabel='Time within final 12 ms',ylabel='Output (V)',title='Settled waveform')
        uniform=np.arange(t[-1]-cfg['analysis_window_s'],t[-1],cfg['maximum_time_step_s'])
        signal=np.interp(uniform,t,v);signal-=signal.mean();window=np.hanning(len(signal))
        amp=2*np.abs(np.fft.rfft(signal*window))/window.sum()
        f=np.fft.rfftfreq(len(signal),cfg['maximum_time_step_s'])
        axes[1].plot(f,20*np.log10(np.maximum(amp,1e-12)/amp.max()))
        axes[1].axvline(int(target),ls='--',color='#a63224',label=f'Target {target} Hz')
        axes[1].set(xlabel='Frequency (Hz)',ylabel='Magnitude (dBc)',xlim=(0,10.5*int(target)),ylim=(-100,5),
                    title='Hann-window FFT; 10 Hz bin spacing')
        axes[1].legend()
        fig.suptitle(f"Verified {target} Hz finalist: R1={row['R1_ohm']/1000:g} kΩ, R2={row['R2_ohm']/1000:g} kΩ, C={row['C_nominal_nF']:g} nF\n"
            f"{row['simulated_frequency_hz']:.3f} Hz, THD {row['thd_2_to_10_percent']:.3f}%; maximum timestep 1.25 µs")
        fig.savefig(folder/f'finalist_{target}Hz.png',dpi=150);plt.close(fig)


if __name__=='__main__':main()
