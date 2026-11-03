"""Audio conversion and a transparent, basic spectral DTMF sanity checker.
The checker is not a standards-compliant receiver model.
"""
from pathlib import Path
import json,wave
import numpy as np
ROWS=np.array([697,770,852,941]);COLS=np.array([1209,1336,1477,1633])
KEYS=['123A','456B','789C','*0#D']


def lowpass_decimate(signal,input_rate,output_rate):
    """Linear-phase windowed-sinc FIR, reflect padding, integer decimation.
    Cutoff=0.45*output_rate; Kaiser beta=8.6; 48 taps per decimation factor.
    This is explicit audio antialiasing, not distortion removal from SPICE data.
    """
    assert input_rate%output_rate==0
    factor=input_rate//output_rate;half=24*factor
    n=np.arange(-half,half+1,dtype=float);cutoff=.45*output_rate/input_rate
    taps=2*cutoff*np.sinc(2*cutoff*n)*np.kaiser(len(n),8.6);taps/=taps.sum()
    filtered=np.convolve(np.pad(signal,(half,half),mode='reflect'),taps,mode='valid')
    return filtered[::factor]


def write_pcm(path,signal,sample_rate,volts_per_fullscale):
    normalized=np.asarray(signal)/volts_per_fullscale
    assert np.max(np.abs(normalized))<1
    pcm=np.rint(normalized*32767).astype('<i2')
    with wave.open(str(path),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(sample_rate);f.writeframes(pcm.tobytes())
    return pcm


def read_pcm(path):
    with wave.open(str(path),'rb') as f:
        assert f.getnchannels()==1 and f.getsampwidth()==2
        fs=f.getframerate();signal=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(float)/32767
    return fs,signal


def decode_basic(signal,fs):
    """40 ms Hann frames, 10 ms hop, 6 dB within-group dominance.
    A group amplitude must exceed 15% of file peak; frames must exceed 10%
    of file peak RMS; valid runs need >=40 ms of frame-start persistence.
    These are declared sanity-check settings, not lab or telecom pass limits.
    """
    signal=np.asarray(signal,float);size=round(.04*fs);hop=round(.01*fs)
    if len(signal)<size:return dict(decoded='',segments=[],settings='40 ms frames; 10 ms hop; basic spectral checker')
    win=np.hanning(size);t=np.arange(size)/fs;freqs=np.r_[ROWS,COLS]
    kernel=np.exp(-2j*np.pi*freqs[:,None]*t)*win[None,:]
    file_peak=np.max(np.abs(signal));labels=[]
    for start in range(0,len(signal)-size+1,hop):
        x=signal[start:start+size];x=x-x.mean();a=2*np.abs(kernel@x)/win.sum()
        label=None
        if file_peak>0 and np.sqrt(np.mean(x*x))>.1*file_peak:
            groups=[a[:4],a[4:]];idx=[int(np.argmax(g)) for g in groups]
            dominant=all(g[k]>.15*file_peak and g[k]>10**(6/20)*np.partition(g,-2)[-2] for g,k in zip(groups,idx))
            if dominant:label=KEYS[idx[0]][idx[1]]
        labels.append((start/fs,label))
    segments=[];current=None;start=None;count=0
    for timestamp,label in labels+[(len(signal)/fs,None)]:
        if label!=current:
            if current is not None and count*hop/fs>=.04:
                segments.append(dict(digit=current,start_s=start,end_s=timestamp))
            current=label;start=timestamp;count=0
        count+=1
    return dict(decoded=''.join(s['digit'] for s in segments),segments=segments,
        settings={'frame_ms':40,'hop_ms':10,'group_dominance_db':6,'minimum_group_amplitude_fraction_of_file_peak':.15,
            'minimum_frame_rms_fraction_of_file_peak':.1,'minimum_frame_start_persistence_ms':40},
        limitation='Basic spectral sanity check, not a certified or device-specific DTMF decoder.')


def export_audio(data,cfg,folder):
    folder.mkdir(parents=True,exist_ok=True);intermediate_rate=960000
    assert intermediate_rate>=1/cfg['maximum_time_step_s']
    times=np.arange(round(cfg['transient_stop_s']*intermediate_rate))/intermediate_rate
    volts=np.interp(times,data['time'],data['v(sum_out)'])
    volts_per_fullscale=float(np.max(np.abs(volts))/cfg['audio_fullscale_nominal_peak'])
    files=[];checks={}
    for fs in cfg['audio_sample_rates_hz']:
        signal=lowpass_decimate(volts,intermediate_rate,fs)
        tail=signal[round(.2*fs):round(.5*fs)];silence=np.zeros(round(.1*fs))
        steady=np.r_[silence,tail,silence]
        repeat=np.r_[silence,tail,np.zeros(round(.15*fs)),tail,np.zeros(round(.15*fs)),tail,silence]
        for label,audio,expected in [('startup',signal,None),('steady',steady,'4'),('repeated',repeat,'444')]:
            path=folder/f'dtmf_4_{label}_{fs//1000}k.wav';write_pcm(path,audio,fs,volts_per_fullscale)
            check_fs,decoded_signal=read_pcm(path);decoded=decode_basic(decoded_signal,check_fs)
            if expected is not None:assert decoded['decoded']==expected,(path,decoded)
            files.append(dict(file=path.name,sample_rate_hz=fs,channels=1,pcm_bits=16,duration_s=len(audio)/fs,
                volts_per_fullscale=volts_per_fullscale,decoded_by_basic_sanity_check=decoded['decoded'],
                source='Actual simulated output, linearly resampled with explicit FIR antialias filter. No sine regeneration, selective harmonic removal, or independent tone normalization; only the documented antialias filter and common linear scaling.'))
            checks[path.name]=decoded
    metadata=dict(expected_digit='4',expected_nominal_frequencies_hz=[770,1209],intermediate_rate_hz=intermediate_rate,
        antialias_filter='Kaiser-windowed sinc; beta 8.6; 48*decimation_factor+1 taps; cutoff 0.45*output_rate; reflect-padded linear convolution.',
        scaling='One common volts-per-fullscale factor from the nominal physical output, shared by every export. Output PCM peak is approximately 0.8 full scale.',
        steady_source_interval_s=[.2,.5],silence_lead_and_trail_s=.1,repeated_between_burst_silence_s=.15,
        remark='Steady and repeated files add digital silence for decoder testing; they do not model switching in the circuit. Prefer the 48 kHz steady file. 8 kHz is provided for narrowband decoders.',files=files)
    (folder/'audio_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (folder/'basic_decoder_check.json').write_text(json.dumps(checks,indent=2)+'\n')
    return metadata
