"""Two physical Wien oscillators and a third TL074 used as an inverting summer.
SI units in netlists and data; no ideal sine sources in the circuit.
"""
from pathlib import Path
import hashlib,itertools,json,math,os,re,subprocess,time,shutil
import numpy as np
from wien_reference import analyze, discover_ngspice, write_csv
ROOT=Path(__file__).resolve().parents[1]


def base_parameters(cfg,step=None,load='configured'):
    return dict(parts={band:{name:list(parts) for name,parts in legs.items()} for band,legs in cfg['oscillator_parts_ohm'].items()},
        capacitors={f'{b}_C{i}':1e-8 for b in ('low','high') for i in (1,2)},
        summer_Rin_low_ohm=cfg['summing_input_resistances_ohm'][0],
        summer_Rin_high_ohm=cfg['summing_input_resistances_ohm'][1],
        summer_Rf_ohm=cfg['summing_feedback_resistance_ohm'],
        output_load_ohm=cfg['output_load_ohm'] if load=='configured' else load,
        step_s=step or cfg['maximum_time_step_s'])


def canonical_parameters(value):
    if isinstance(value,dict):return {k:canonical_parameters(v) for k,v in value.items()}
    if isinstance(value,list):return [canonical_parameters(v) for v in value]
    if isinstance(value,(int,float)):return float(f'{value:.14g}')
    return value


def identify(p):
    canonical=json.dumps(canonical_parameters(p),sort_keys=True,separators=(',',':'))
    return 'case_'+hashlib.sha256(canonical.encode()).hexdigest()[:16]


def grid_rows(cfg):
    """Separate factorial R, C and summer studies; other groups held nominal."""
    rows=[]
    for study,nvars in [('oscillator_R',4),('oscillator_C',4),('summing_R',3)]:
        tolerances=cfg['capacitor_tolerance_percent_scenarios'] if study=='oscillator_C' else cfg['resistor_tolerance_percent_scenarios']
        for tol in tolerances:
            for levels in itertools.product((-1,0,1),repeat=nvars):
                p=base_parameters(cfg,cfg['tolerance_grid_timestep_s'])
                offsets=[tol*x for x in levels]
                if study=='oscillator_R':
                    for (band,leg),offset in zip(itertools.product(('low','high'),('R1','R2')),offsets):
                        p['parts'][band][leg]=[v*(1+offset/100) for v in p['parts'][band][leg]]
                elif study=='oscillator_C':
                    for key,offset in zip(cfg['capacitor_positions'],offsets):p['capacitors'][key]*=1+offset/100
                else:
                    for key,offset in zip(('summer_Rin_low_ohm','summer_Rin_high_ohm','summer_Rf_ohm'),offsets):p[key]*=1+offset/100
                row=dict(study=study,tolerance_percent=tol,offsets_percent=json.dumps(offsets),all_nominal=all(l==0 for l in levels),parameters=p,case_id=identify(p))
                rows.append(row)
    # Limited joint stress cases: each oscillator's two R legs move together and
    # its two capacitors move together. Not a full 11-dimensional component grid.
    for signs in itertools.product((-1,1),repeat=4):
        p=base_parameters(cfg,cfg['tolerance_grid_timestep_s'])
        for b,rs,cs in zip(('low','high'),signs[:2],signs[2:]):
            for leg in ('R1','R2'):p['parts'][b][leg]=[v*(1+rs*.01) for v in p['parts'][b][leg]]
            for i in (1,2):p['capacitors'][f'{b}_C{i}']*=1+cs*.10
        rows.append(dict(study='combined_selected_corners_R1pct_C10pct',tolerance_percent=None,offsets_percent=json.dumps(signs),all_nominal=False,parameters=p,case_id=identify(p)))
    return rows


def physical_columns(p):
    row={k:v for k,v in p.items() if k not in ('parts','capacitors')}
    row.update(p['capacitors'])
    for band,legs in p['parts'].items():
        for leg,parts in legs.items():
            row[f'{band}_{leg}_total_ohm']=sum(parts)
            for i,value in enumerate(parts,1):row[f'{band}_{leg}_{i}_ohm']=value
    return row


def oscillator_lines(band,p,cfg):
    lines=[f'X{band} {band}_wien {band}_inv vcc vee {band}_out TL074']
    for leg,start,end in [('R1',f'{band}_out',f'{band}_series_rc'),('R2',f'{band}_wien','0')]:
        parts=p['parts'][band][leg]
        for i,value in enumerate(parts):
            a=start if i==0 else f'{band}_{leg}_junction{i}'
            b=end if i==len(parts)-1 else f'{band}_{leg}_junction{i+1}'
            lines.append(f'R{band}_{leg}_{i+1} {a} {b} {value:.14g}')
    lines += [f'C{band}_1 {band}_series_rc {band}_wien {p["capacitors"][band+"_C1"]:.14g}',
        f'C{band}_2 {band}_wien 0 {p["capacitors"][band+"_C2"]:.14g}',
        f'R{band}_g {band}_inv 0 {cfg["gain_ground_resistance_ohm"]:.14g}',
        f'R{band}_f_fixed {band}_out {band}_diode {cfg["gain_feedback_fixed_ohm"]:.14g}',
        f'R{band}_f_bypassed {band}_diode {band}_inv {cfg["gain_feedback_bypassed_ohm"]:.14g}',
        f'X{band}_dpositive {band}_diode {band}_inv 1N4148',
        f'X{band}_dnegative {band}_inv {band}_diode 1N4148']
    start,duration=cfg['seed_start_s'],cfg['seed_duration_s']
    lines.append(f'I{band}_seed 0 {band}_wien PWL(0 0 {start:.14g} 0 {start+1e-6:.14g} {cfg["seed_current_a"]:.14g} {start+duration:.14g} {cfg["seed_current_a"]:.14g} {start+duration+1e-6:.14g} 0)')
    return lines


def write_netlist(p,cfg,folder):
    folder.mkdir(parents=True,exist_ok=True)
    models=Path(os.path.relpath(ROOT/'models',folder))
    lines=['Two refined Wien oscillators and TL074 summing amplifier',
        '* Subcircuit pin order is (+,-,V+,V-,output), not DIP pin numbering.',
        f'.include "{models/"TL074_ngspice.lib"}"',f'.include "{models/"1N4148.lib"}"',
        f'Vpositive vcc 0 {cfg["supply_magnitude_v"]:.14g}',f'Vnegative vee 0 {-cfg["supply_magnitude_v"]:.14g}']
    for band in ('low','high'):lines+=oscillator_lines(band,p,cfg)
    lines += [f'Rsum_in_low low_out sum_inv {p["summer_Rin_low_ohm"]:.14g}',
        f'Rsum_in_high high_out sum_inv {p["summer_Rin_high_ohm"]:.14g}',
        f'Rsum_feedback sum_out sum_inv {p["summer_Rf_ohm"]:.14g}',
        'Xsum 0 sum_inv vcc vee sum_out TL074',
        '* Unused fourth channel: + input grounded, output connected to - input.',
        'Xunused 0 unused_out vcc vee unused_out TL074',
        '* Supply bypass capacitors from the partner BOM, across ideal rails.',
        'Cdec_pos vcc 0 100n','Cdec_neg vee 0 100n','Cbulk_pos vcc 0 10u','Cbulk_neg vee 0 10u']
    if p['output_load_ohm'] is not None:lines.append(f'Rscope sum_out 0 {p["output_load_ohm"]:.14g}')
    cap=cfg.get('scope_input_capacitance_f')
    if cap:lines.append(f'Cscope sum_out 0 {cap:.14g}')
    lines += [f'.temp {cfg["temperature_c"]:.14g}',
        '.options reltol=1e-5 abstol=1e-10 vntol=1e-7 method=trap',
        '.save v(low_out) v(high_out) v(sum_out) v(sum_inv) v(unused_out)',
        f'.tran {p["step_s"]:.14g} {cfg["transient_stop_s"]:.14g} 0 {p["step_s"]:.14g}', '.end']
    netlist=folder/'circuit.cir';netlist.write_text('\n'.join(lines)+'\n');return netlist


def read_raw_multi(path):
    data=Path(path).read_bytes();header,binary=data.split(b'Binary:\n',1);header=header.decode('ascii',errors='replace')
    nvars=int(re.search(r'No\. Variables:\s*(\d+)',header).group(1));npoints=int(re.search(r'No\. Points:\s*(\d+)',header).group(1))
    assert re.search(r'Flags:.*real',header)
    variables=re.findall(r'^\s*\d+\s+(\S+)\s+\S+\s*$',header.split('\nVariables:\n',1)[1],re.MULTILINE)
    assert len(variables)==nvars
    values=np.frombuffer(binary,dtype=np.float64).reshape(npoints,nvars)
    assert np.all(np.isfinite(values)) and np.all(np.diff(values[:,0])>=0)
    keep=np.r_[True,np.diff(values[:,0])>0]
    return {name:values[keep,i].copy() for i,name in enumerate(variables)}


def two_tone_fit(t,v,frequencies):
    tt=t-t[0];cols=[np.ones_like(tt)]
    for f in frequencies:cols += [np.sin(2*np.pi*f*tt),np.cos(2*np.pi*f*tt)]
    matrix=np.column_stack(cols);coefs=np.linalg.lstsq(matrix,v,rcond=None)[0]
    return coefs,matrix@coefs


def measure(data,p,cfg):
    t=data['time'];local_cfg=dict(cfg,maximum_time_step_s=p['step_s'])
    result={}
    for band,target in [('low',770),('high',1209)]:
        m=analyze(t,data[f'v({band}_out)'],{'target_hz':target},local_cfg)
        result.update({f'{band}_{k}':v for k,v in m.items()})
    mask=t>=cfg['transient_stop_s']-cfg['analysis_window_s'];ta=t[mask];out=data['v(sum_out)'][mask]
    low=data['v(low_out)'][mask];high=data['v(high_out)'][mask]
    expected=-p['summer_Rf_ohm']*(low/p['summer_Rin_low_ohm']+high/p['summer_Rin_high_ohm'])
    error=out-expected;error_ac=error-np.mean(error)
    result.update(output_peak_to_peak_v=float(np.ptp(out)),output_dc_v=float(np.mean(out)),output_peak_abs_v=float(np.max(np.abs(out))),
        output_rms_v=float(np.sqrt(np.mean(out*out))),ideal_summing_error_rms_v=float(np.sqrt(np.mean(error_ac**2))),
        ideal_summing_error_dc_v=float(np.mean(error)),ideal_summing_error_peak_v=float(np.max(np.abs(error_ac))),
        output_near_supply_rail=bool(np.max(np.abs(out))>=.95*cfg['supply_magnitude_v']),
        ideal_rail_margin_v=cfg['supply_magnitude_v']-float(np.max(np.abs(out))),
        summing_node_peak_abs_v=float(np.max(np.abs(data['v(sum_inv)'][mask]))),
        unused_output_peak_abs_v=float(np.max(np.abs(data['v(unused_out)'][mask]))),
        nominal_gain_low=-p['summer_Rf_ohm']/p['summer_Rin_low_ohm'],nominal_gain_high=-p['summer_Rf_ohm']/p['summer_Rin_high_ohm'])
    result['both_oscillators_settled']=all(result[f'{b}_oscillation_status']=='settled_oscillation' for b in ('low','high'))
    fs=[result[f'{b}_simulated_frequency_hz'] for b in ('low','high')]
    if all(f is not None for f in fs):
        stride=max(1,len(ta)//5000);ts=ta[::stride];ys=out[::stride]
        coefs,fitted=two_tone_fit(ts,ys,fs)
        amps=np.hypot(coefs[1::2],coefs[2::2]);fund_rms=float(np.sqrt(np.sum(amps**2)/2))
        result.update(output_low_fundamental_peak_v=float(amps[0]),output_high_fundamental_peak_v=float(amps[1]),
            output_twist_high_over_low_db=float(20*np.log10(amps[1]/amps[0])),
            residual_to_two_fundamentals_percent=100*float(np.sqrt(np.mean((ys-fitted)**2)))/fund_rms,
            summing_error_relative_fundamentals_percent=100*result['ideal_summing_error_rms_v']/fund_rms)
        for i,(band,signal) in enumerate([('low',low[::stride]),('high',high[::stride])]):
            ci,_=two_tone_fit(ts,signal,fs)
            z_out=complex(coefs[1+2*i],coefs[2+2*i]);z_in=complex(ci[1+2*i],ci[2+2*i]);ratio=z_out/z_in
            result[f'measured_gain_{band}_magnitude']=abs(ratio);result[f'measured_gain_{band}_phase_deg']=math.degrees(np.angle(ratio))
        # Multi-sine fit separates harmonics from a small specified set of mixing products.
        harmonics=[h*f for f in fs for h in range(2,11)]
        mixing=[abs(fs[1]-fs[0]),sum(fs),abs(2*fs[0]-fs[1]),2*fs[0]+fs[1],abs(2*fs[1]-fs[0]),2*fs[1]+fs[0]]
        allfreq=fs+harmonics+mixing
        c,_=two_tone_fit(ts,ys,allfreq);a=np.hypot(c[1::2],c[2::2]);ref=np.sqrt(np.sum(a[:2]**2))
        result['output_harmonics_2_to_10_relative_combined_fundamentals_percent']=100*float(np.linalg.norm(a[2:20]))/ref
        result['selected_mixing_products_relative_fundamentals_percent']=100*float(np.linalg.norm(a[20:]))/ref
    return result


def run_case(p,cfg,executable,results,keep=False):
    cid=identify(p);folder=results/'cases'/cid;folder.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(json.dumps({'parameters':canonical_parameters(p),'config':cfg},sort_keys=True).encode())
    for path in [Path(__file__),ROOT/'src/wien_reference.py',ROOT/'models/TL074_ngspice.lib',ROOT/'models/1N4148.lib']:digest.update(path.read_bytes())
    stamp=digest.hexdigest();cache=folder/'metrics.json';raw=folder/'waveform.raw'
    if cache.exists():
        old=json.loads(cache.read_text())
        if old.get('fingerprint')==stamp and old.get('simulation_status')=='ok' and (not keep or raw.exists()):return old
    write_netlist(p,cfg,folder)
    env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',SPICE_ASCIIRAWFILE='0')
    lib=Path(executable).parent.parent/'lib/ngspice/spice2poly.cm'
    if lib.exists():
        # ngspice codemodel does not unquote filenames consistently. Use a local alias.
        alias=folder/'spice2poly.cm'
        alias.unlink(missing_ok=True)
        try:alias.symlink_to(lib.resolve())
        except OSError:shutil.copyfile(lib,alias)
        (folder/'spinit').write_text('* Explicit local POLY support\nset filetype=binary\nset num_threads=1\ncodemodel ./spice2poly.cm\n')
        env['SPICE_SCRIPTS']=str(folder)
    start=time.perf_counter()
    try:
        proc=subprocess.run([executable,'-n','-b','-r','waveform.raw','-o','ngspice.log','circuit.cir'],cwd=folder,env=env,capture_output=True,text=True,timeout=cfg['per_case_timeout_s'])
        (folder/'console.log').write_text(proc.stdout+proc.stderr)
        if proc.returncode!=0 or not raw.exists():raise RuntimeError(f'ngspice exit {proc.returncode}; inspect {folder}')
        result=measure(read_raw_multi(raw),p,cfg);result['simulation_status']='ok'
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired,AssertionError) as exc:
        result={'simulation_status':'simulation_failed','error':str(exc)}
    result.update(case_id=cid,fingerprint=stamp,elapsed_wall_s=time.perf_counter()-start)
    cache.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    if raw.exists() and not keep:raw.unlink()
    return result
