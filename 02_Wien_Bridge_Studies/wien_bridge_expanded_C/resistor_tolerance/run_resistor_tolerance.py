#!/usr/bin/env python3
"""Run physical resistor tolerance grids using the existing oscillator/model core."""
from pathlib import Path
import concurrent.futures as futures
import csv, hashlib, itertools, json, sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from wien import discover_ngspice, run_case, network_theory, physical_key, write_csv


def build_rows(selected):
    rows=[]
    for target,chosen in selected.items():
        target=int(target)
        parts=[float(x) for name in ('R1','R2') for x in chosen[f'{name}_parts_ohm'].split(' + ')]
        assert len(parts)==4
        for tol in (.01,.05,.10):
            for levels in itertools.product((-1,0,1),repeat=4):
                actual=[p*(1+tol*l) for p,l in zip(parts,levels)]
                row=dict(target_hz=target,resistor_tolerance_percent=100*tol,
                    R1_nominal_ohm=sum(parts[:2]),R2_nominal_ohm=sum(parts[2:]),
                    R1_ohm=sum(actual[:2]),R2_ohm=sum(actual[2:]),
                    R1_parts_ohm=' + '.join(f'{p:.14g}' for p in actual[:2]),
                    R2_parts_ohm=' + '.join(f'{p:.14g}' for p in actual[2:]),
                    C1_f=1e-8,C2_f=1e-8,resistors_nominal=all(l==0 for l in levels),
                    coherent_per_leg=(levels[0]==levels[1] and levels[2]==levels[3]))
                for name,p,a,l in zip(('R1_1','R1_2','R2_1','R2_2'),parts,actual,levels):
                    row.update({f'{name}_nominal_ohm':p,f'{name}_actual_ohm':a,f'{name}_offset_percent':100*tol*l})
                row.update(R1_offset_percent=100*(row['R1_ohm']/row['R1_nominal_ohm']-1),
                    R2_offset_percent=100*(row['R2_ohm']/row['R2_nominal_ohm']-1))
                freq,gain=network_theory(row['R1_ohm'],row['R2_ohm'],1e-8,1e-8)
                row.update(theory_zero_phase_hz=freq,theory_required_gain=gain,
                    case_id=f'r{target}_'+hashlib.sha256(json.dumps(physical_key(row)).encode()).hexdigest()[:12])
                rows.append(row)
    return rows


def make_plots(rows,summaries):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    from matplotlib.patches import Rectangle
    folder=HERE/'figures';folder.mkdir(exist_ok=True)
    for target in (770,1209):
        rr=[r for r in rows if r['target_hz']==target]
        nominal=next(r for r in rr if r['resistors_nominal'])
        fig,axes=plt.subplots(1,3,figsize=(16,7.8))
        good=[r for r in rr if r.get('oscillation_status')=='settled_oscillation']
        limit=max(abs(r['simulated_signed_error_percent']) for r in good)
        norm=TwoSlopeNorm(vmin=-limit,vcenter=0,vmax=limit)
        for ax,tol in zip(axes,(1,5,10)):
            subset=[r for r in rr if r['resistor_tolerance_percent']==tol and r['coherent_per_leg']]
            assert len(subset)==9
            values=np.full((3,3),np.nan);lookup={}
            for r in subset:
                i=(-tol,0,tol).index(round(r['R2_1_offset_percent'],8));j=(-tol,0,tol).index(round(r['R1_1_offset_percent'],8))
                lookup[i,j]=r
                if r.get('oscillation_status')=='settled_oscillation':values[i,j]=r['simulated_signed_error_percent']
            cm=plt.get_cmap('RdBu_r').copy();cm.set_bad('#d8dce1')
            im=ax.imshow(values,cmap=cm,norm=norm,origin='lower',aspect='auto')
            for (i,j),r in lookup.items():
                if np.isfinite(values[i,j]):
                    txt=f"{r['simulated_frequency_hz']:.2f} Hz\n{values[i,j]:+.2f}%";color='white' if abs(values[i,j])>.6*limit else '#142536'
                else:txt='Not settled' if r.get('oscillation_status')!='no_sustained_oscillation' else 'No sustained\noscillation';color='#142536'
                ax.text(j,i,txt,ha='center',va='center',fontsize=10,color=color)
            ax.add_patch(Rectangle((.52,.52),.96,.96,fill=False,edgecolor='#f0b500',lw=2.5))
            r1=nominal['R1_nominal_ohm'];r2=nominal['R2_nominal_ohm']
            ax.set_xticks(range(3),[f'{r1*(1+l*tol/100)/1000:.3f}' for l in (-1,0,1)])
            ax.set_yticks(range(3),[f'{r2*(1+l*tol/100)/1000:.3f}' for l in (-1,0,1)])
            ax.set_xlabel('Actual total R1 (kΩ)',labelpad=8)
            ax.set_ylabel('Actual total R2 (kΩ)',labelpad=6)
            ax.set_title(f'±{tol}% resistor tolerance\n−{tol}%, nominal, +{tol}%',fontsize=12,pad=12)
            ax.set_xticks(np.arange(-.5,3),minor=True);ax.set_yticks(np.arange(-.5,3),minor=True);ax.grid(which='minor',color='white',lw=2);ax.tick_params(which='minor',left=False,bottom=False)
        fig.subplots_adjust(left=.07,right=.89,top=.78,bottom=.33,wspace=.34)
        cax=fig.add_axes([.915,.29,.015,.43]);fig.colorbar(im,cax=cax,label='Signed frequency error (%)')
        fig.suptitle(f'{target} Hz oscillator: R1 and R2 tolerance',fontsize=20,y=.97,fontweight='bold')
        fig.text(.5,.875,f"R1 = {nominal['R1_nominal_ohm']/1000:g} kΩ; R2 = {nominal['R2_nominal_ohm']/1000:g} kΩ; C1 = C2 = 10 nF (fixed)",ha='center',fontsize=13)
        fig.text(.07,.17,'Each panel shows coherent −tolerance / nominal / +tolerance shifts within each series pair.\nR1 and R2 vary independently. Gold = nominal; gray = no settled oscillation.\nAll 81 combinations of the four physical resistors per tolerance are included in the CSV.',fontsize=11,linespacing=1.6,color='#3b4d5f')
        fig.text(.07,.035,'TL074 supplied model • ±12 V • 27 °C • 0.5 s transient • maximum timestep 1.25 µs\n±1%, ±5%, ±10% are part-tolerance scenarios; E24/E12 identify nominal value series.',fontsize=10,color='#3b4d5f',linespacing=1.5)
        fig.savefig(folder/f'resistor_tolerance_{target}Hz.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,5.8))
    for ax,target in zip(axes,(770,1209)):
        rr=[s for s in summaries if s['target_hz']==target]
        nominal=next(r for r in rows if r['target_hz']==target and r['resistors_nominal'])['simulated_frequency_hz']
        for i,r in enumerate(rr):
            ax.plot([r['minimum_settled_frequency_hz'],r['maximum_settled_frequency_hz']],[i,i],lw=8,solid_capstyle='round',color='#90bed0')
            ax.plot(nominal,i,'o',color='#143b50',ms=7)
            midpoint=(r['minimum_settled_frequency_hz']+r['maximum_settled_frequency_hz'])/2
            ax.text(midpoint,i+.22,f"{r['minimum_settled_frequency_hz']:.2f}–{r['maximum_settled_frequency_hz']:.2f} Hz",ha='center',fontsize=10)
        ax.axvline(target,ls='--',color='#b33427',label=f'Target {target} Hz')
        ax.plot([],[],'o',color='#143b50',label=f'Nominal {nominal:.2f} Hz')
        ax.set_yticks(range(3),[f"±{r['resistor_tolerance_percent']:g}%\n{r['settled_rows']}/81 settled" for r in rr]);ax.set_ylim(2.95,-.6)
        ax.set_xlabel('Simulated frequency (Hz)');ax.set_title(f'{target} Hz oscillator',fontsize=15);ax.grid(axis='x',alpha=.2);ax.legend(loc='lower right',fontsize=9);ax.margins(x=.12)
    fig.suptitle('Frequency ranges from independent physical-resistor tolerance samples',fontsize=16,fontweight='bold',y=.97)
    fig.text(.08,.035,'C1 = C2 = 10 nF fixed. Ranges show sampled settled results, not a statistical yield or continuous-domain guarantee.\nEach tolerance scenario tests 3⁴ = 81 combinations: four physical resistors, each at −tolerance, nominal, +tolerance.',fontsize=10,color='#3b4d5f',linespacing=1.6)
    fig.subplots_adjust(left=.09,right=.98,top=.83,bottom=.23,wspace=.26)
    fig.savefig(folder/'resistor_tolerance_frequency_ranges.png',dpi=180);plt.close(fig)


def main():
    cfg=json.loads((ROOT/'config.json').read_text());cfg['maximum_time_step_s']=1.25e-6
    selected=json.loads((ROOT/'selected_nominal_values.json').read_text())['oscillators']
    rows=build_rows(selected);unique={r['case_id']:r for r in rows}
    (HERE/'config_used.json').write_text(json.dumps(cfg,indent=2)+'\n')
    exe=discover_ngspice();measurements={}
    print(f'{len(rows)} scenario rows; {len(unique)} unique circuits',flush=True)
    with futures.ThreadPoolExecutor(max_workers=8) as pool:
        jobs={pool.submit(run_case,r,cfg,exe,HERE):cid for cid,r in unique.items()}
        for n,job in enumerate(futures.as_completed(jobs),1):
            measurements[jobs[job]]=job.result()
            if n%40==0 or n==len(jobs):print(f'{n}/{len(jobs)} circuits complete',flush=True)
    joined=[dict(r,**measurements[r['case_id']]) for r in rows]
    assert all(r['simulation_status']=='ok' for r in joined)
    summary=[]
    for target in (770,1209):
        rr=[r for r in joined if r['target_hz']==target]
        write_csv(HERE/f'resistor_tolerance_{target}Hz.csv',rr)
        nominal=next(r for r in rr if r['resistors_nominal'])
        assert abs(nominal['simulated_frequency_hz']-selected[str(target)]['simulated_frequency_hz'])<1e-6
        for tol in (1,5,10):
            group=[r for r in rr if r['resistor_tolerance_percent']==tol];assert len(group)==81
            settled=[r for r in group if r['oscillation_status']=='settled_oscillation'];assert settled
            low=min(settled,key=lambda r:r['simulated_frequency_hz']);high=max(settled,key=lambda r:r['simulated_frequency_hz'])
            summary.append(dict(target_hz=target,resistor_tolerance_percent=tol,scenario_rows=len(group),settled_rows=len(settled),
                nonsettled_rows=len(group)-len(settled),nominal_frequency_hz=nominal['simulated_frequency_hz'],
                minimum_settled_frequency_hz=low['simulated_frequency_hz'],maximum_settled_frequency_hz=high['simulated_frequency_hz'],
                minimum_case_id=low['case_id'],maximum_case_id=high['case_id'],
                minimum_settled_vpp_v=min(r['steady_state_vpp_v'] for r in settled),maximum_settled_vpp_v=max(r['steady_state_vpp_v'] for r in settled),
                minimum_settled_thd_percent=min(r['thd_2_to_10_percent'] for r in settled),maximum_settled_thd_percent=max(r['thd_2_to_10_percent'] for r in settled)))
    write_csv(HERE/'resistor_tolerance_summary.csv',summary)
    # Check actual discrete resistor values written into every unique circuit.
    for cid,row in unique.items():
        text=(HERE/'cases'/cid/'circuit.cir').read_text()
        for name in ('R1','R2'):
            parts=[float(v) for v in row[f'{name}_parts_ohm'].split(' + ')]
            assert np.isclose(sum(parts),row[f'{name}_ohm'],rtol=1e-13)
            for i,p in enumerate(parts,1):
                line=next(line for line in text.splitlines() if line.startswith(f'{name}_{i} '))
                assert np.isclose(float(line.split()[-1]),p,rtol=1e-13)
    make_plots(joined,summary)
    validation=dict(scenario_rows=len(joined),unique_circuits=len(unique),simulator_failures=0,
        nominal_frequencies_reproduce_final_selected_values=True,physical_resistor_netlists_checked=True,
        models_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'models').glob('*.lib')},
        src_wien_sha256=hashlib.sha256((ROOT/'src/wien.py').read_bytes()).hexdigest(),
        summary=summary)
    (HERE/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
