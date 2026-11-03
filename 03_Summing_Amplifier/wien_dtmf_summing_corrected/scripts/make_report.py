#!/usr/bin/env python3
"""Render measured results, native waveforms, portable CSVs, and coverage checks."""
from pathlib import Path
from collections import Counter
import csv,hashlib,html,json,sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from summing import read_raw_multi,write_csv,grid_rows,physical_columns
from audio_export import export_audio


def typed(s):
    if s=='':return None
    if s in ('True','False'):return s=='True'
    try:return float(s)
    except ValueError:return s


def read_csv(path):
    with path.open() as f:return [{k:typed(v) for k,v in r.items()} for r in csv.DictReader(f)]


def summarize(rows):
    output=[]
    keys=sorted({(r['study'],r['tolerance_percent'] or 0) for r in rows})
    metrics=['low_simulated_frequency_hz','high_simulated_frequency_hz','output_peak_to_peak_v',
        'output_twist_high_over_low_db','measured_gain_low_magnitude','measured_gain_high_magnitude',
        'residual_to_two_fundamentals_percent','summing_error_relative_fundamentals_percent']
    for study,tol in keys:
        rr=[r for r in rows if r['study']==study and (r['tolerance_percent'] or 0)==tol]
        good=[r for r in rr if r['simulation_status']=='ok' and r['both_oscillators_settled']]
        row=dict(study=study,tolerance_percent=tol or None,scenario_rows=len(rr),both_settled_rows=len(good),
            simulator_failures=sum(r['simulation_status']!='ok' for r in rr),
            near_rail_rows=sum(bool(r.get('output_near_supply_rail')) for r in rr))
        for key in metrics:
            values=[r[key] for r in good if r.get(key) is not None]
            row['minimum_'+key]=min(values) if values else None;row['maximum_'+key]=max(values) if values else None
        output.append(row)
    return output


def plot_nominal(data,p,m,cfg):
    folder=ROOT/'figures';folder.mkdir(exist_ok=True)
    t=data['time'];out=data['v(sum_out)'];low=data['v(low_out)'];high=data['v(high_out)']
    fig,axes=plt.subplots(3,1,figsize=(12,10),constrained_layout=True)
    axes[0].plot(t*1000,out,color='#126b70',lw=.65)
    axes[0].set(xlabel='Time (ms)',ylabel='Summed output (V)',title='Startup: full simulated 0.5 s')
    tail=t>=t[-1]-.012;tx=(t[tail]-t[-1]+.012)*1000
    axes[1].plot(tx,low[tail],label='Low oscillator',alpha=.7,lw=1)
    axes[1].plot(tx,high[tail],label='High oscillator',alpha=.7,lw=1)
    axes[1].plot(tx,out[tail],label='Summed output',color='#126b70',lw=1.6)
    axes[1].set(xlabel='Time within final 12 ms',ylabel='Voltage (V)',title='Settled inputs and output');axes[1].legend(ncol=3,fontsize=9,loc='upper right')
    tu=np.arange(cfg['transient_stop_s']-cfg['analysis_window_s'],cfg['transient_stop_s'],p['step_s'])
    vu=np.interp(tu,t,out);vu-=vu.mean();win=np.hanning(len(vu))
    amp=2*np.abs(np.fft.rfft(vu*win))/win.sum();freq=np.fft.rfftfreq(len(vu),p['step_s'])
    ref=max(m['output_low_fundamental_peak_v'],m['output_high_fundamental_peak_v']);db=20*np.log10(np.maximum(amp,1e-16)/ref)
    axes[2].plot(freq,db,color='#126b70',lw=1)
    for f,color in [(770,'#356ba5'),(1209,'#d36f27')]:axes[2].axvline(f,ls='--',color=color,lw=1,label=f'Target {f} Hz')
    axes[2].set(xlim=(0,15000),ylim=(-120,5),xlabel='Frequency (Hz)',ylabel='Magnitude (dB relative to larger tone)',title='Output spectrum: Hann window, 10 Hz FFT bins');axes[2].legend(fontsize=9)
    fig.suptitle(f"Two Wien oscillators + inverting summer — high R1=13.082 kΩ, R2=13.110 kΩ\n{m['low_simulated_frequency_hz']:.2f} Hz + {m['high_simulated_frequency_hz']:.2f} Hz; output {m['output_peak_to_peak_v']:.3f} Vpp; twist {m['output_twist_high_over_low_db']:+.3f} dB",fontsize=16)
    fig.savefig(folder/'nominal_waveform_and_fft.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,5),constrained_layout=True)
    ax.semilogx(freq[1:],db[1:],color='#126b70',lw=.8)
    for f in (770,1209):ax.axvline(f,color='#b34a32',ls='--',lw=.8)
    ax.set(xlim=(10,freq[-1]),ylim=(-200,5),xlabel='Frequency (Hz), logarithmic scale',ylabel='Magnitude (dB relative to larger tone)',
        title='Summed output: full available FFT bandwidth')
    ax.grid(alpha=.2);fig.suptitle('Finite-window spectrum; no transient noise injected',fontsize=13)
    fig.savefig(folder/'fft_wideband.png',dpi=160);plt.close(fig)
    start=t[-1]-.008;mask=t>=start;tt=(t[mask]-start)*1000
    ideal=-p['summer_Rf_ohm']*(low/p['summer_Rin_low_ohm']+high/p['summer_Rin_high_ohm'])
    err=out-ideal
    fig,axes=plt.subplots(2,1,figsize=(11,6),constrained_layout=True)
    axes[0].plot(tt,ideal[mask],color='#d57528',ls='--',lw=2,label='Ideal weighted sum of actual inputs')
    axes[0].plot(tt,out[mask],color='#126b70',lw=1,label='Actual TL074 output')
    axes[0].set(ylabel='Output (V)',title='Actual sum and ideal sum overlap at this scale');axes[0].legend(fontsize=9)
    axes[1].plot(tt,1000*err[mask],color='#7a3f83');axes[1].set(xlabel='Time within final 8 ms',ylabel='Actual − ideal (mV)',title='Finite gain and phase leave a small summing error')
    fig.suptitle(f"Nominal summer: Rin = 22 kΩ per input; Rf = 10 kΩ\nAC summing-error RMS {1000*m['ideal_summing_error_rms_v']:.3f} mV ({m['summing_error_relative_fundamentals_percent']:.4f}% of combined fundamental RMS)",fontsize=14)
    fig.savefig(folder/'summing_linearity.png',dpi=160);plt.close(fig)
    waves=ROOT/'waveforms';waves.mkdir(exist_ok=True)
    np.savetxt(waves/'nominal_native.csv',np.column_stack((t,low,high,out)),delimiter=',',fmt='%.12g',header='time_s,low_oscillator_v,high_oscillator_v,summed_output_v',comments='')
    np.savetxt(waves/'nominal_fft.csv',np.column_stack((freq,amp,db)),delimiter=',',fmt='%.12g',header='frequency_hz,amplitude_v_peak,magnitude_db_relative_larger_fundamental',comments='')


def range_plot(summary,rows,study,title,filename,kind='frequency'):
    fig,axes=plt.subplots(1,2,figsize=(13,6.2))
    rr=[r for r in summary if r['study']==study]
    grid_nom=next(r for r in rows if r['study']==study and r['all_nominal'])
    for ax,band,target in zip(axes,('low','high'),(770,1209)):
        key=f'{band}_simulated_frequency_hz' if kind=='frequency' else f'measured_gain_{band}_magnitude'
        nominal=grid_nom[key]
        for i,r in enumerate(rr):
            lo,hi=r['minimum_'+key],r['maximum_'+key]
            ax.plot([lo,hi],[i,i],color='#87b8ca',lw=9,solid_capstyle='round')
            ax.plot(nominal,i,'o',color='#163d51',ms=7)
            text=f'{lo:.2f}–{hi:.2f} Hz' if kind=='frequency' else f'{lo:.5f}–{hi:.5f}'
            ax.text((lo+hi)/2,i+.23,text,ha='center',fontsize=10,bbox=dict(facecolor='white',edgecolor='none',alpha=.8,pad=1))
        ax.axvline(target if kind=='frequency' else 10/22,color='#b04b32',ls='--',lw=1.3,label=f'Target {target} Hz' if kind=='frequency' else 'Ideal nominal gain 10/22')
        ax.plot([],[],'o',color='#163d51',label=f'Nominal grid: {nominal:.2f} Hz' if kind=='frequency' else f'Nominal grid: {nominal:.5f}')
        ax.set_yticks(range(len(rr)),[f"±{r['tolerance_percent']:g}%\n{r['both_settled_rows']}/{r['scenario_rows']} settled" for r in rr])
        ax.set_ylim(2.95,-.6);ax.set_title(f'{target} Hz tone',fontsize=15);ax.set_xlabel('Simulated frequency (Hz)' if kind=='frequency' else 'Measured output/input fundamental gain magnitude')
        ax.grid(axis='x',alpha=.2);ax.margins(x=.16);ax.legend(loc='lower right',fontsize=8)
    fig.suptitle(title,fontsize=16,y=.97,fontweight='bold')
    note={'oscillator_R':'Four effective Wien resistances vary independently; both physical parts within a series pair shift together. Capacitors and summer resistors stay nominal.',
        'oscillator_C':'All four oscillator capacitors vary independently. Frequency-setting resistors and summer resistors stay nominal.',
        'summing_R':'Both 22 kΩ summing inputs and the 10 kΩ feedback resistor vary independently. Oscillator parts stay nominal.'}[study]
    fig.text(.075,.065,note,fontsize=9,color='#42556a',wrap=True)
    fig.text(.075,.025,'Ranges are measured settled samples, not probability intervals. Tolerance grid maximum timestep 5 µs; nominal WAV/report uses 1.25 µs.',fontsize=9,color='#42556a')
    fig.subplots_adjust(left=.09,right=.98,top=.84,bottom=.23,wspace=.28)
    fig.savefig(ROOT/'figures'/filename,dpi=160);plt.close(fig)


def main():
    cfg=json.loads((ROOT/'config.json').read_text());nom=json.loads((ROOT/'results/nominal.json').read_text());p=nom['parameters'];m=nom['measurement']
    data=read_raw_multi(ROOT/'results/cases'/m['case_id']/'waveform.raw')
    rows=read_csv(ROOT/'results/tolerance_all.csv');summary=summarize(rows);write_csv(ROOT/'results/tolerance_summary.csv',summary)
    checks=read_csv(ROOT/'results/numerical_and_load_checks.csv')
    plot_nominal(data,p,m,cfg)
    range_plot(summary,rows,'oscillator_R','Wien-resistor tolerance with both oscillators connected to the summer','oscillator_resistor_tolerance.png')
    range_plot(summary,rows,'oscillator_C','Capacitor tolerance with both oscillators connected to the summer','capacitor_tolerance.png')
    range_plot(summary,rows,'summing_R','Summing-resistor tolerance: per-tone gain range','summing_resistor_tolerance.png',kind='gain')
    meta=export_audio(data,cfg,ROOT/'audio')
    baseline=json.loads((ROOT/'reference/selected_nominal_values.json').read_text())['oscillators']
    comparisons=[]
    for band,target in [('low',770),('high',1209)]:
        old=baseline[str(target)]['simulated_frequency_hz'];new=m[f'{band}_simulated_frequency_hz']
        comparisons.append(dict(target_hz=target,standalone_frequency_hz=old,loaded_frequency_hz=new,loading_shift_hz=new-old,
            frequency_error_percent=100*(new-target)/target,measured_gain_magnitude=m[f'measured_gain_{band}_magnitude'],
            measured_gain_phase_deg=m[f'measured_gain_{band}_phase_deg']))
    write_csv(ROOT/'results/standalone_vs_connected.csv',comparisons)
    # Actual emitted netlists establish physical coverage independently of typed
    # integer/float JSON identifiers. Nominal duplicates are retained as evidence.
    definitions=grid_rows(cfg);assert len(rows)==len(definitions)==583
    expected=Counter((r['study'],r['tolerance_percent']) for r in definitions)
    actual=Counter((r['study'],r['tolerance_percent']) for r in rows);assert expected==actual
    unique={r['case_id']:r for r in definitions};netlist_hashes=set()
    for cid,r in unique.items():
        folder=ROOT/'results/cases'/cid;metrics=json.loads((folder/'metrics.json').read_text())
        assert metrics['simulation_status']=='ok'
        text=(folder/'circuit.cir').read_text();netlist_hashes.add(hashlib.sha256(text.encode()).hexdigest())
        netparts={line.split()[0]:float(line.split()[-1]) for line in text.splitlines() if line.startswith(('Rlow_R','Rhigh_R','Clow_','Chigh_','Rsum_'))}
        pp=r['parameters']
        for b,legs in pp['parts'].items():
            for leg,parts in legs.items():
                for i,value in enumerate(parts,1):assert np.isclose(netparts[f'R{b}_{leg}_{i}'],value,rtol=1e-13)
        for b in ('low','high'):
            for i in (1,2):assert np.isclose(netparts[f'C{b}_{i}'],pp['capacitors'][f'{b}_C{i}'],rtol=1e-13,atol=0)
        for nk,pk in [('Rsum_in_low','summer_Rin_low_ohm'),('Rsum_in_high','summer_Rin_high_ohm'),('Rsum_feedback','summer_Rf_ohm')]:assert np.isclose(netparts[nk],pp[pk],rtol=1e-13)
    validation=dict(scenario_rows=len(rows),tolerance_case_runs=len(unique),distinct_emitted_tolerance_netlists=len(netlist_hashes),
        simulator_failures=sum(r['simulation_status']!='ok' for r in rows),both_settled_rows=sum(r['both_oscillators_settled'] for r in rows),
        near_supply_rail_rows=sum(r['output_near_supply_rail'] for r in rows),native_trace_points=len(data['time']),
        physical_netlist_component_values_verified=True,full_factorial_scenario_counts_verified=True,
        models_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (ROOT/'models').glob('*.lib')},
        source_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (ROOT/'src').glob('*.py')},
        note='Physical parameter identities are normalized to the 14 significant digits written to SPICE; equivalent integer/float representations share the same cached circuit.',
        nominal=m,numerical_and_load_checks=checks)
    assert validation['simulator_failures']==0
    (ROOT/'results/validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    build_overview(m,summary,checks,comparisons,validation)
    print(json.dumps({k:validation[k] for k in ('scenario_rows','tolerance_case_runs','distinct_emitted_tolerance_netlists','simulator_failures','both_settled_rows','near_supply_rail_rows')},indent=2))


def build_overview(m,summary,checks,comparisons,validation):
    lines=['# Two Wien oscillators + summing amplifier: results','',
        '**Decoder file:** [dtmf_4_steady_48k.wav](audio/dtmf_4_steady_48k.wav). Intended digit: **4**. Basic spectral checker returns **4**; repeated WAV returns **444** at both 48 kHz and 8 kHz. These are checks of the exported model waveform, not certification of a particular DTMF decoder.','',
        'The summer follows the partner calculation: **22 kΩ per input, 10 kΩ feedback**, nominal gain **−0.454545 per tone**. It uses the final refined oscillator components. The fourth TL074 channel is grounded as a follower.','',
        'The 1209 Hz resistor choice is pinned to **R1=13,082 Ω / R2=13,110 Ω**. Nominal results below use **1.25 µs** maximum timestep. The original standalone table used **5 µs**; see [matching-timestep comparisons](results/timestep_and_loading_comparison.csv) for numerical and loading effects with the components held fixed.','',
        '## Nominal connected circuit','',
        '| Target | R1 | R2 | C1=C2 | Standalone frequency | Connected frequency | Shift from loading |','|---:|---|---|---:|---:|---:|---:|']
    for r,parts in zip(comparisons,[('20 kΩ + 620 Ω','20 kΩ + 560 Ω'),('13 kΩ + 82 Ω','13 kΩ + 110 Ω')]):
        lines.append(f"| {r['target_hz']} Hz | {parts[0]} | {parts[1]} | 10 nF | {r['standalone_frequency_hz']:.4f} Hz | {r['loaded_frequency_hz']:.4f} Hz | {r['loading_shift_hz']:+.4f} Hz |")
    lines+=['',f"Output: **{m['output_peak_to_peak_v']:.3f} Vpp**, peak ±approximately {m['output_peak_abs_v']:.3f} V; external load **1 MΩ**. Twist (high/low): **{m['output_twist_high_over_low_db']:+.3f} dB**. Both oscillators settle by approximately 20 ms under the original bin-based settling measure.",'',
        f"Measured per-tone gain magnitudes: {m['measured_gain_low_magnitude']:.6f} and {m['measured_gain_high_magnitude']:.6f}, with phases {m['measured_gain_low_phase_deg']:.3f}° and {m['measured_gain_high_phase_deg']:.3f}°. The nominal summer does not approach the supply rails in this simulation.",'',
        f"The source oscillators retain approximately 3.8% THD from their diode amplitude control. The summed waveform's RMS residual to two fundamental sine waves is {m['residual_to_two_fundamentals_percent']:.3f}%; this is not single-tone THD. Comparing actual output with the ideal weighted sum gives **{1000*m['ideal_summing_error_rms_v']:.3f} mV AC RMS error**, predominantly finite-gain/phase behavior.",'',
        '![Nominal waveform and FFT](figures/nominal_waveform_and_fft.png)','',
        '## Tolerance results','',
        'Other component groups stay nominal in each separate study. The grids use 5 µs maximum timestep. The numerical/WAV nominal uses 1.25 µs. These ranges describe sampled settled cases; they are not receiver pass limits or manufacturing yields.','',
        '| Study | Tolerance | Settled / rows | Low frequency range (Hz) | High frequency range (Hz) | Output Vpp range | Twist range (dB) |','|---|---:|---:|---:|---:|---:|---:|']
    titles={'oscillator_R':'Wien R1/R2','oscillator_C':'Four capacitors','summing_R':'Summer resistors','combined_selected_corners_R1pct_C10pct':'Joint selected corners'}
    for r in summary:
        tol=f"±{r['tolerance_percent']:g}%" if r['tolerance_percent'] else 'R ±1%, C ±10%'
        fmt=lambda key,dp=2:f"{r['minimum_'+key]:.{dp}f}–{r['maximum_'+key]:.{dp}f}" if r['minimum_'+key] is not None else 'none'
        lines.append(f"| {titles[r['study']]} | {tol} | {r['both_settled_rows']}/{r['scenario_rows']} | {fmt('low_simulated_frequency_hz')} | {fmt('high_simulated_frequency_hz')} | {fmt('output_peak_to_peak_v')} | {fmt('output_twist_high_over_low_db')} |")
    lines+=['','The BOM specifies 1% resistors, so ±1% is the primary resistor case. The previous user-specified 10% capacitor tolerance remains the primary capacitor case. Large capacitor tolerance can move the tone frequencies substantially despite the accurate nominal resistor choices; no claim is made that every tolerance case decodes as 4.','',
        '![Summer resistor tolerance](figures/summing_resistor_tolerance.png)','',
        '![Wien resistor tolerance](figures/oscillator_resistor_tolerance.png)','',
        '![Capacitor tolerance](figures/capacitor_tolerance.png)','',
        '## Numerical and load checks','',
        '| Check | Low tone (Hz) | High tone (Hz) | Output Vpp | Both settled |','|---|---:|---:|---:|---|']
    for r in checks:lines.append(f"| {r['check']} | {r['low_simulated_frequency_hz']:.4f} | {r['high_simulated_frequency_hz']:.4f} | {r['output_peak_to_peak_v']:.4f} | {r['both_oscillators_settled']} |")
    lines+=['',f"Coverage: **{validation['scenario_rows']} tolerance scenario rows**, **{validation['tolerance_case_runs']} tolerance transient runs**, zero simulator failures. {validation['both_settled_rows']} rows have both oscillators settled; {validation['near_supply_rail_rows']} output rows reach the analysis rail guard. Every emitted physical part value is checked against its scenario definition.",'',
        '## Files to use','',
        '- Decoder input: [steady 48 kHz WAV](audio/dtmf_4_steady_48k.wav), [repeated 48 kHz WAV](audio/dtmf_4_repeated_48k.wav), [steady 8 kHz WAV](audio/dtmf_4_steady_8k.wav).',
        '- Main netlist: [circuit.cir](circuits/nominal/circuit.cir).',
        '- Native time/voltage data: [nominal_native.csv](waveforms/nominal_native.csv).',
        f"- Native ngspice raw waveform: [waveform.raw](results/cases/{m['case_id']}/waveform.raw).",
        '- Detailed data: [all tolerance rows](results/tolerance_all.csv), [summary](results/tolerance_summary.csv), [load/numerical checks](results/numerical_and_load_checks.csv).',
        '- More plots: [summing linearity](figures/summing_linearity.png), [wideband FFT](figures/fft_wideband.png).',
        '- Assumptions, reproduction and decoder details: [README](README.md).','']
    (ROOT/'SUMMARY.md').write_text('\n'.join(lines))
    h=['<!doctype html><html><head><meta charset="utf-8"><title>Wien DTMF summing results</title><style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 24px;color:#183044}img{width:100%;height:auto}table{border-collapse:collapse;width:100%}td,th{padding:9px;border:1px solid #cad5dd;text-align:left}a{color:#096f8a}audio{width:100%}</style></head><body>',
        '<h1>Wien oscillators + TL074 summing amplifier</h1>',
        f"<p><strong>{m['low_simulated_frequency_hz']:.2f} Hz + {m['high_simulated_frequency_hz']:.2f} Hz; {m['output_peak_to_peak_v']:.3f} Vpp into 1 MΩ.</strong></p>",
        '<p>Summer: 22 kΩ at each input, 10 kΩ feedback. High oscillator: R1=13,082 Ω, R2=13,110 Ω. Nominal waveform timestep 1.25 µs; original 5 µs table is separately checked without changing components.</p>',
        '<p><a href="SUMMARY.md">Detailed results</a> · <a href="README.md">Assumptions and running instructions</a> · <a href="circuits/nominal/circuit.cir">SPICE netlist</a></p>',
        '<h2>DTMF decoder input: digit 4</h2><p><a href="audio/dtmf_4_steady_48k.wav">Download steady WAV (48 kHz)</a> · <a href="audio/dtmf_4_repeated_48k.wav">Repeated 444</a> · <a href="audio/dtmf_4_steady_8k.wav">8 kHz alternative</a></p>',
        '<audio controls src="audio/dtmf_4_steady_48k.wav"></audio>',
        '<p>Actual simulated output, common volume scaling and explicit audio antialiasing. Basic spectral checker returns 4; it is not a test of your specific decoder.</p>']
    for name,label in [('nominal_waveform_and_fft.png','Nominal waveform and spectrum'),('summing_resistor_tolerance.png','Summing resistor tolerance'),('oscillator_resistor_tolerance.png','Wien resistor tolerance'),('capacitor_tolerance.png','Capacitor tolerance'),('summing_linearity.png','Summing accuracy'),('fft_wideband.png','Wideband spectrum')]:h.append(f'<h2>{label}</h2><img src="figures/{name}" alt="{label}">')
    h+=['<p><a href="results/tolerance_all.csv">All tolerance CSV</a> · <a href="waveforms/nominal_native.csv">Native voltage CSV</a> · <a href="audio/audio_metadata.json">Audio calibration</a></p></body></html>']
    (ROOT/'START_HERE.html').write_text('\n'.join(h))

if __name__=='__main__':main()
