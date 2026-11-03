"""Read-only analysis of copied lab evidence. Python: numpy, openpyxl; Node: sharp.
Run: python 04_Skrip/analyze.py (NODE_BIN may override the node executable on PATH).
All numeric outputs use measured files, with provenance and explicit diagnostics.
"""
from pathlib import Path
import csv,hashlib,json,math,os,subprocess,wave,html,shutil
import numpy as np
import openpyxl
P=Path(__file__).resolve().parents[1];D=P/'01_Data_Asli';R=P/'02_Hasil_Analisis';G=P/'03_Grafik'
NODE=os.environ.get('NODE_BIN') or shutil.which('node')
if not NODE:raise SystemExit('Node.js not found. Install Node.js or set NODE_BIN to its executable.')
# Check rendering dependency before writing any analysis outputs.
subprocess.run([NODE,'-e',"require(process.env.SHARP_MODULE || 'sharp')"],cwd=P/'04_Skrip',check=True)
R.mkdir(parents=True,exist_ok=True);G.mkdir(parents=True,exist_ok=True)
wb=openpyxl.load_workbook(D/'Lembar_Pengujian_Wien_DTMF.xlsx',data_only=True)
extract={s.title:[{'row':r[0].row,'values':[c.value for c in r]} for r in s if any(c.value is not None for c in r)] for s in wb}
(R/'workbook_data_tersimpan.json').write_text(json.dumps(extract,ensure_ascii=False,indent=2))
s=wb['Pengukuran lab'];c=wb['Komponen dan koneksi'];v=lambda r:s[f'D{r}'].value
def writecsv(name,rows):
    with (R/name).open('w',newline='') as f:
        q=csv.DictWriter(f,fieldnames=list(rows[0]));q.writeheader();q.writerows(rows)
def fit(t,x,freqs,harmonics=1):
    a=[np.ones_like(t)]
    for f in freqs:
        for k in range(1,harmonics+1):a.extend([np.cos(2*np.pi*f*k*t),np.sin(2*np.pi*f*k*t)])
    A=np.array(a).T;b=np.linalg.lstsq(A,x,rcond=None)[0];res=x-A@b
    amps=np.hypot(b[1::2],b[2::2]).reshape(len(freqs),harmonics)
    return float(res@res),amps,float(np.sqrt(np.mean(res**2)))
def golden(fn,lo,hi):
    k=(math.sqrt(5)-1)/2;a=hi-k*(hi-lo);b=lo+k*(hi-lo);fa=fn(a);fb=fn(b)
    for _ in range(35):
        if fa<fb:hi,b,fb=b,a,fa;a=hi-k*(hi-lo);fa=fn(a)
        else:lo,a,fa=a,b,fb;b=lo+k*(hi-lo);fb=fn(b)
    return (lo+hi)/2
def estimate(t,x,bands):
    dt=(t[-1]-t[0])/(len(t)-1);nfft=2**math.ceil(math.log2(len(x)*8));xf=np.interp(np.linspace(t[0],t[-1],len(t)),t,x);sp=np.abs(np.fft.rfft((xf-xf.mean())*np.hanning(len(x)),nfft));ff=np.fft.rfftfreq(nfft,dt)
    freq=[]
    for lo,hi in bands:
        ids=np.flatnonzero((ff>=lo)&(ff<=hi));freq.append(float(ff[ids[np.argmax(sp[ids])]]))
    tt=t[::4]-t[0];xx=x[::4]
    for _ in range(5):
        for j in range(len(freq)):
            def objective(z):
                f=freq.copy();f[j]=z;return fit(tt,xx,f)[0]
            freq[j]=golden(objective,freq[j]-8,freq[j]+8)
    return freq,ff,2*sp/np.hanning(len(x)).sum()
records=[];traces={};spectra={};fits={}
for name,role,bands in [('NewFile0.csv','summer',[(700,820),(1100,1280)]),('NewFile1.csv','osilator_rendah',[(700,820)]),('NewFile2.csv','osilator_tinggi',[(1100,1280)])]:
    a=np.loadtxt(D/'Rekaman_Osiloskop'/name,delimiter=',',skiprows=2,usecols=(0,1));t,x=a.T;assert np.all(np.diff(t)>0)
    fs=(len(t)-1)/(t[-1]-t[0]);freq,ff,sp=estimate(t,x,bands);_,amps,res=fit(t-t[0],x,freq,10);traces[role]=(t-t[0],x);spectra[role]=(ff,sp);fits[role]=(freq,amps)
    for i,f in enumerate(freq):
        records.append(dict(file=name,role=role,tone='low' if f<1000 else 'high',samples=len(t),duration_s=float(t[-1]-t[0]),sample_rate_hz=float(fs),frequency_fit_hz=f,frequency_error_percent=(f/([770,1209][f>1000])-1)*100,fundamental_peak_v=float(amps[i,0]),fundamental_rms_v=float(amps[i,0]/np.sqrt(2)),fundamental_dbvrms=float(20*np.log10(amps[i,0]/np.sqrt(2))),thd_2_to_10_fit_percent=float(100*np.linalg.norm(amps[i,1:])/amps[i,0]),trace_vpp_v=float(np.ptp(x)),trace_dc_v=float(x.mean()),fit_residual_rms_v=res))
writecsv('metrik_dari_CSV.csv',records)
wavpath=D/'1-NewFile0_DTMF_48k.wav'
with wave.open(str(wavpath)) as z:
    rate=z.getframerate();assert z.getsampwidth()==2 and z.getnchannels()==1;pcm=np.frombuffer(z.readframes(z.getnframes()),dtype='<i2').astype(float)/32767
nz=np.flatnonzero(np.abs(pcm)>1e-4);first,last=nz[0],nz[-1];active=pcm[first:last+1];ta=np.arange(len(active))/rate
wf,wff,wsp=estimate(ta,active,[(700,820),(1100,1280)]);_,wa,wres=fit(ta,active,wf,10)
# Preserve the actual supplied WAV. An 8 kHz intermediate exists only for JS replay.
factor=6;half=144;n=np.arange(-half,half+1);fc=3600/rate;h=2*fc*np.sinc(2*fc*n)*np.kaiser(len(n),8.6);h/=h.sum();y=np.convolve(np.pad(pcm,(half,half),mode='reflect'),h,mode='valid')[::factor]
(R/'pcm_8k_untuk_replay.json').write_text(json.dumps(dict(sample_rate_hz=8000,samples=y.tolist())))
subprocess.run([NODE,str(P/'04_Skrip/replay_decoder.cjs')],check=True)
replay=json.loads((R/'replay_decoder.json').read_text())
frames=replay['frames'];best=max(frames,key=lambda a:min(a['energies']['770'],a['energies']['1209']))
wavmetrics=dict(source=wavpath.name,sample_rate_hz=rate,samples=len(pcm),file_duration_s=len(pcm)/rate,active_span_s=len(active)/rate,active_start_s=first/rate,pcm_peak=float(np.max(abs(pcm))),estimated_frequencies_hz=wf,twist_db=float(20*np.log10(wa[1,0]/wa[0,0])),voltage_scale_note='PCM is normalized; WAV has no physical volt calibration without CSV conversion factor.',best_joint_frame=best)
(R/'wav_metrics.json').write_text(json.dumps(wavmetrics,indent=2))
# Recompute workbook-derived values independently, retaining discrepancies.
metrics=[dict(metric='Error f rendah workbook',value=(v(36)/770-1)*100,unit='%',source='Pengukuran lab!D36'),dict(metric='Error f tinggi workbook',value=(v(45)/1209-1)*100,unit='%',source='Pengukuran lab!D45'),dict(metric='Gain rendah FFT workbook',value=10**((v(68)-v(66))/20),unit='V/V',source='Pengukuran lab!D66,D68'),dict(metric='Gain tinggi FFT workbook',value=10**((v(69)-v(67))/20),unit='V/V',source='Pengukuran lab!D67,D69'),dict(metric='Twist FFT workbook',value=v(69)-v(68),unit='dB',source='Pengukuran lab!D68:D69')]
for label,r in [('rendah',25),('tinggi',26)]:metrics.append(dict(metric='Gain dari R terukur '+label,value=c['D27'].value/c[f'D{r}'].value,unit='V/V',source=f'Komponen dan koneksi!D27/D{r}'))
writecsv('perhitungan_workbook.csv',metrics)
csv_gains=[]
for band,srcrole in [('low','osilator_rendah'),('high','osilator_tinggi')]:
    output=next(a for a in records if a['role']=='summer' and a['tone']==band)
    source=next(a for a in records if a['role']==srcrole)
    gain=output['fundamental_peak_v']/source['fundamental_peak_v']
    csv_gains.append(dict(tone=band,gain_magnitude=gain,gain_db=20*math.log10(gain),source=source['file'],output='NewFile0.csv',limitation='Separate captures; meaningful if circuit and acquisition conditions unchanged.'))
writecsv('gain_dari_fit_CSV.csv',csv_gains)
component=[]
for r in range(5,34):
    nom=c[f'B{r}'].value;act=c[f'D{r}'].value;tol=c[f'E{r}'].value
    if isinstance(nom,(float,int)) and isinstance(act,(float,int)):
        err=(act/nom-1)*100;component.append(dict(component=c[f'A{r}'].value,nominal=nom,measured=act,unit=c[f'C{r}'].value,deviation_percent=err,listed_tolerance_percent=tol,outside_listed_tolerance=bool(abs(err)>tol) if isinstance(tol,(float,int)) else '',source=f'Komponen dan koneksi!B{r}:E{r}',measurement_method='Not documented: in-circuit vs isolated unknown'))
writecsv('komponen_terukur.csv',component)
# Screenshot values are transcribed, not silently substituted into workbook.
screens=[dict(file='NewFile5.bmp',metric='low frequency',value=769.2,unit='Hz'),dict(file='NewFile5.bmp',metric='low Vpp',value=5.6,unit='V'),dict(file='NewFile8.bmp',metric='high frequency',value=1190,unit='Hz'),dict(file='NewFile8.bmp',metric='high Vpp',value=4.56,unit='V'),dict(file='NewFile7.bmp',metric='low FFT fundamental cursor',value=3.2,unit='dBVrms'),dict(file='NewFile10.bmp',metric='high FFT fundamental cursor',value=1.6,unit='dBVrms'),dict(file='NewFile3.bmp',metric='summer low FFT cursor',value=-.8,unit='dBVrms'),dict(file='NewFile3.bmp',metric='summer high FFT cursor',value=-4,unit='dBVrms')]
writecsv('transkripsi_screenshot.csv',screens)
summary=dict(csv=records,csv_gains=csv_gains,wav=wavmetrics,workbook_calculations=metrics,public_decoder_sweep=replay['sweep'],user_report={'digit':'4','threshold_condition':'<0.01','at_threshold_0_1':'not detected','attempt_count':None,'evidence':'User report; no decoder screenshot supplied'},analysis_date='2026-10-29',method='Variable-frequency joint least-squares sine/cosine fit; CSV timestamps used, harmonic fit orders 1–10; estimates depend on CSV time calibration. Windowed FFT only for visualization, zero padding does not improve true resolution.')
(R/'analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps({'csv_metrics':records,'wav':wavmetrics,'component_exceptions':[i for i in component if i['outside_listed_tolerance']]},indent=2))
def table(headers,rows):return '<table><thead><tr>'+''.join('<th>'+html.escape(str(i))+'</th>' for i in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(i))+'</td>' for i in row)+'</tr>' for row in rows)+'</tbody></table>'
csvtable=table(['Rekaman','Nada','Durasi (ms)','f fit (Hz)','Error (%)','Vpp rekaman (V)','Fundamental (Vrms)'],[[q['file'],q['tone'],f"{q['duration_s']*1000:.2f}",f"{q['frequency_fit_hz']:.2f}",f"{q['frequency_error_percent']:+.2f}",f"{q['trace_vpp_v']:.2f}",f"{q['fundamental_rms_v']:.3f}"] for q in records])
sweeptable=table(['Threshold','Decoded — replay lokal'],[[i['threshold'],i['decoded'] or '(kosong)'] for i in replay['sweep']])
worktable=table(['Parameter','Nilai','Satuan'],[[a['metric'],f"{a['value']:.5f}",a['unit']] for a in metrics])
exceptiontable=table(['Komponen','Nominal','Terukur','Deviasi (%)','Toleransi tertulis (%)'],[[a['component'],a['nominal'],a['measured'],f"{a['deviation_percent']:+.2f}",a['listed_tolerance_percent']] for a in component if a['outside_listed_tolerance']])
readme=f'''# Analisis hasil uji Wien DTMF — digit 4

Mulai dari **00_MULAI_DI_SINI.html**. Dokumen HTML bisa dibuka tanpa internet.

- 01_Data_Asli: salinan workbook, WAV pendek, CSV dan screenshot asli; tidak disunting.
- 02_Hasil_Analisis: angka hasil analisis, kalkulasi dan replay decoder lokal.
- 03_Grafik: grafik waveform dan spektrum, ringkasan PNG serta screenshot PNG.
- 04_Skrip: analisis yang dapat dijalankan ulang (Python numpy/openpyxl, Node sharp).
- 05_Kode_Decoder_Publik: salinan kode publik dtmf.netlify.app diambil 29 Oktober 2026.

Hasil website: pengguna melaporkan digit 4 hanya saat threshold <0,01. Ini disimpan sebagai laporan pengguna, bukan klaim pengujian browser baru. Hasil replay lokal dicatat terpisah.
WAV asli tidak disetel ulang frekuensinya. Sumber lengkap dan hash ada di manifest.json.
'''
(P/'README.md').write_text(readme)
report=f'''<!doctype html><html lang="id"><meta charset="utf-8"><title>Analisis hasil uji DTMF 4</title><style>body{{font:16px/1.55 Arial,sans-serif;color:#203247;max-width:1120px;margin:40px auto;padding:0 24px}}h1,h2{{color:#173955}}h2{{margin-top:36px}}table{{border-collapse:collapse;width:100%;margin:18px 0;font-size:14px}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #d9e2eb}}th{{background:#e8eef4}}.note{{padding:18px;background:#fff3d4;border-left:4px solid #c28a12}}img{{max-width:100%;height:auto}}a{{color:#14569a}}code{{background:#f0f3f5;padding:2px 5px}}</style>
<h1>Analisis hasil uji Wien DTMF — digit 4</h1><p>Analisis 29 Oktober 2026. Scope pada workbook: Rigol DS1052E. Multimeter: CD800a.</p>
<p class="note"><b>Hasil utama:</b> pengguna melaporkan WAV pendek terdeteksi sebagai <b>4 pada threshold &lt;0,01</b>, tetapi tidak pada 0,1. Itu membuktikan deteksi pada pengaturan tersebut, belum membuktikan kesesuaian semua parameter DTMF. Jumlah percobaan dan nilai threshold tepat belum dicatat.</p>
<p><a href="03_Grafik/ringkasan.png">Ringkasan PNG</a> · <a href="01_Data_Asli/1-NewFile0_DTMF_48k.wav">WAV yang diuji</a> · <a href="01_Data_Asli/Lembar_Pengujian_Wien_DTMF.xlsx">Workbook asli</a> · <a href="02_Hasil_Analisis/analysis.json">Hasil numerik lengkap</a></p>
<h2>1. Pengukuran yang dicatat</h2><p>Workbook berisi osilator rendah {v(36)} Hz / {v(38)} Vpp, osilator tinggi {v(45)} Hz / {v(47)} Vpp, dan output summer {v(56)} Vpp / {v(60)} Vrms. Tidak ada clipping menurut catatan pengguna. Pembanding simulasi summer 5,548 Vpp tidak menjadi batas kelulusan.</p>{worktable}
<p>Gain di atas berasal dari cursor FFT workbook. Dari resistor summer terukur, prediksi ideal magnitudo gain sekitar {metrics[5]['value']:.4f} dan {metrics[6]['value']:.4f}, sedangkan desain nominal 0,4545. Perbedaan dengan gain FFT belum dapat langsung dianggap kesalahan summer karena pembacaan cursor dan kondisi antar-rekaman perlu disamakan.</p>
<h2>2. Verifikasi dari CSV dan WAV asli</h2>{csvtable}
<p>Frekuensi dihitung langsung dari sumbu waktu CSV dengan fitting sinus, bukan dari jarak cursor screenshot. Hasil CSV sekitar {wf[0]:.1f} dan {wf[1]:.1f} Hz menjelaskan adanya perbedaan terhadap target 770 dan 1209 Hz. Angka workbook/screenshot dan CSV berasal dari rekaman berbeda; belum diketahui apakah pengaturan atau komponen berubah antar-pengambilan. Jangan mengganti angka workbook diam-diam dengan angka CSV.</p>
<p>Rasio fundamental hasil fit antar-CSV memberi magnitudo gain rendah <b>{csv_gains[0]['gain_magnitude']:.4f}</b> dan tinggi <b>{csv_gains[1]['gain_magnitude']:.4f}</b> V/V. Ini lebih dekat ke desain dibanding gain cursor workbook, tetapi berasal dari capture terpisah dan hanya bisa dibandingkan jika kondisi rangkaian/probe tidak berubah. Ini bukan alasan untuk langsung mengganti resistor summer berdasarkan cursor FFT saja.</p>
<p>WAV: 48 kHz, mono, PCM 16-bit; panjang file {len(pcm)/rate:.6f} s. Rentang sinyal aktif {len(active)/rate*1000:.2f} ms, sisanya silence. Peak PCM {wavmetrics['pcm_peak']:.3f} full scale; twist hasil fit WAV {wavmetrics['twist_db']:+.2f} dB. WAV tidak memiliki satuan volt; pengukuran tegangan tetap mengacu CSV/scope.</p>
<audio controls src="01_Data_Asli/1-NewFile0_DTMF_48k.wav"></audio><img src="03_Grafik/waveform_dan_fft.png" alt="Waveform dan FFT rekaman">
<p>Spektrum memakai Hann window; resolusi asli summer sekitar {1/records[0]['duration_s']:.2f} Hz. Zero padding hanya memperhalus plot. THD pada CSV dihitung fit harmonik ke-2–10 dan disimpan dalam CSV hasil; residual juga mengandung noise, kuantisasi, dan ketidakcocokan model, sehingga bukan ukuran noise murni.</p>
<h2>3. Apa sebenarnya arti threshold pada website?</h2>
<p>Kode publik website memakai Goertzel pada delapan frekuensi nominal DTMF. Setiap frame berisi 320 sampel; halaman meminta audio context 8 kHz, sehingga frame nominalnya 40 ms. Sinyal diberi exact Blackman window. Untuk masing-masing kandidat:</p>
<p><code>E(f) = power_Goertzel(f) / totalPower_windowed / jumlah_sampel</code></p>
<p>Decoder memilih kandidat terbesar di grup rendah dan tinggi yang melewati threshold. Jadi threshold adalah <b>skor spektral relatif tanpa satuan</b>, bukan volt, dBV, atau langsung amplitudo PCM. Mengalikan seluruh WAV dengan faktor k mengalikan pembilang dan penyebut dengan k²; skornya secara ideal tetap sama. Pernyataan lama bahwa threshold hanya menerima nada lebih lemah perlu diperbaiki menjadi: menerima skor relatif yang lebih kecil pada frekuensi nominal.</p>
<p>Detuning (frekuensi aktual bergeser), ketidakseimbangan kedua nada, durasi/posisi frame dan energi harmonik/noise dapat menurunkan skor kandidat. Dalam data ini nada tinggi WAV berbeda cukup jauh dari 1209 Hz, sehingga masuk akal skor bin 1209 lebih kecil. Ini penjelasan berbasis data dan algoritme, bukan bukti bahwa hanya satu faktor menjadi penyebab.</p>
<p>Kode ini tidak menambahkan pemeriksaan eksplisit batas error frekuensi, twist, atau persistensi multi-frame. Karena itu karakter 4 pada threshold kecil tidak berarti sinyal telah lolos pengujian penerima DTMF standar.</p>
<h2>4. Replay lokal kode decoder yang sama</h2>{sweeptable}
<p>Ini <b>replay lokal</b>, bukan pengujian ulang pada browser pengguna. WAV diresample offline ke 8 kHz memakai FIR; implementasi resampling WebAudio dapat menghasilkan sedikit perbedaan. Frame terbaik bersama (awal {best['start_s']:.3f} s): E770 = {best['energies']['770']:.6f}; E1209 = {best['energies']['1209']:.6f}. Threshold 0,1 harus dilampaui oleh kedua kandidat sekaligus. Uji pengali amplitudo 0,1× / 0,5× / 1× / 2× pada replay dicatat di JSON; penskalaan tanpa clipping tidak mengubah rasio energi.</p>
<h2>5. Perbedaan data yang harus ditandai</h2><ul>
<li><b>Level FFT rendah:</b> workbook D66 = +4,0 dBVrms, tetapi NewFile7.bmp memperlihatkan +3,2 dB pada cursor. Jika memakai +3,2, gain rendah menjadi −4,0 dB (0,6310 V/V), bukan −4,8 dB. Belum dipilih salah satunya sebagai hasil pasti.</li>
<li><b>Vpp:</b> workbook rendah 5,76 V, NewFile5.bmp 5,60 V; workbook tinggi 4,64 V, NewFile8.bmp 4,56 V. Bisa berbeda capture; catat waktu/kondisinya.</li>
<li><b>Offset CSV rendah:</b> NewFile1.csv memiliki rata-rata sekitar +0,467 V, berbeda dari workbook −0,0427 V dan screenshot NewFile5.bmp sekitar +0,135 mV. Offset tidak dipaksa sama; fitting menyertakan konstanta DC.</li>
<li><b>Rail negatif:</b> workbook D31 tertulis +11,98 V pada baris target −12 V. Tanda dan arah probe perlu dikonfirmasi; tidak diasumsikan supply benar-benar positif.</li>
<li><b>Arus supply 0 mA:</b> kemungkinan pembulatan atau placeholder, belum bukti konsumsi arus nol. Resolusi alat belum dicatat.</li>
<li><b>Catatan lama:</b> baris 70/109 masih menyebut summer rendah −1,6 dBV, sedangkan input terbaru D68 = −0,8 dBV. Analisis workbook memakai D68 terbaru dan mempertahankan catatan lama sebagai riwayat.</li>
<li><b>Komponen di luar toleransi tertulis:</b> beberapa resistor terukur menyimpang lebih dari 1%. Belum dicatat apakah pengukuran in-circuit atau kaki dilepas. Jangan langsung menyimpulkan part rusak/toleransi salah.</li></ul>{exceptiontable}
<h2>6. Langkah pengujian berikutnya</h2><ol><li>Simpan screenshot decoder dan nilai threshold tepat yang berhasil. Ulangi beberapa kali pada file dan setting sama; catat berhasil/total tanpa mengarang hitungan.</li><li>Konfirmasi sumber frekuensi tinggi: ukur lagi pada pin 7 dan pin 8. Hindari mengubah frekuensi WAV agar terbaca; sesuaikan rangkaian bila diperlukan.</li><li>Untuk capture 500 ms–1 s, pastikan CSV memuat ≥20 kSa/s (≥10.000 sampel per 500 ms). Time/div saja tidak menjamin jumlah sampel ekspor. Rekaman panjang 600 titik pada 1 kSa/s dari pengujian sebelumnya tidak dipakai sebagai bukti spektrum DTMF.</li><li>Ulangi empat level FFT pada pengaturan sama, lalu cocokkan pembacaan cursor dengan workbook. Konfirmasi tanda rail negatif dan metode ukur resistor.</li></ol>
<h2>Sumber dan reproduksibilitas</h2><p>Data eksperimen disalin ke 01_Data_Asli. Pemetaan file: NewFile0.csv = summer; NewFile1.csv = osilator rendah; NewFile2.csv = osilator tinggi, sesuai workbook. Buka screenshot asli untuk memverifikasi cursor. Analisis tidak mengubah sumber.</p><p>Kode resmi aplikasi publik: <a href="https://dtmf.netlify.app">halaman decoder</a>, <a href="https://dtmf.netlify.app/DTMFDecoder.js">DTMFDecoder.js</a>, <a href="https://dtmf.netlify.app/Goertzel.js">Goertzel.js</a>. Salinan di 05_Kode_Decoder_Publik. Dependensi dan metode ada pada 04_Skrip/analyze.py. Hash sumber dan hasil ada di manifest.json.</p></html>'''
(P/'00_MULAI_DI_SINI.html').write_text(report)
# SVG plots with actual coordinates; convert via the bundled sharp renderer.
def esc(x):return html.escape(str(x))
def svg_start(width,height):return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/><g font-family="Arial,sans-serif" fill="#203247">']
def text(a,x,y,label,size=22,color='#203247'):a.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}">{esc(label)}</text>')
def plot(a,x,y,width,height,xx,yy,xlim,ylim,title,xlab,ylab,color='#167c97'):
    text(a,x,y-22,title,24)
    for q in np.linspace(ylim[0],ylim[1],5):
        Y=y+height-(q-ylim[0])/(ylim[1]-ylim[0])*height;a.append(f'<path d="M{x},{Y}h{width}" stroke="#dce5ed"/>');text(a,x-65,Y+6,f'{q:.1f}',17)
    for q in np.linspace(xlim[0],xlim[1],7):text(a,x+(q-xlim[0])/(xlim[1]-xlim[0])*width-15,y+height+27,f'{q:.1f}' if xlim[1]<100 else f'{q:.0f}',17)
    mask=(xx>=xlim[0])&(xx<=xlim[1]);X=xx[mask];Y=yy[mask];stride=max(1,len(X)//3000);X=X[::stride];Y=Y[::stride];points=' '.join(f'{x+(u-xlim[0])/(xlim[1]-xlim[0])*width:.2f},{y+height-(np.clip(v,ylim[0],ylim[1])-ylim[0])/(ylim[1]-ylim[0])*height:.2f}' for u,v in zip(X,Y));a.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.8"/>');text(a,x+width/2-45,y+height+58,xlab,19);text(a,x,y-48,ylab,18)
a=svg_start(1500,1370);text(a,70,55,'Hasil rekaman summer: waveform dan spektrum',32)
t,x=traces['summer'];plot(a,110,150,1300,250,t*1000,x,(0,t[-1]*1000),(-2.6,2.6),'Rekaman lengkap NewFile0.csv','Waktu (ms)','Tegangan (V)')
plot(a,110,570,1300,250,t*1000,x,(0,12),(-2.6,2.6),'Pembesaran 12 ms','Waktu (ms)','Tegangan (V)')
ff,sp=spectra['summer'];db=20*np.log10(np.maximum(sp,1e-10)/np.sqrt(2));plot(a,110,990,1300,250,ff,db,(0,5000),(-65,10),'FFT Hann — level fundamental dan harmonik','Frekuensi (Hz)','Magnitudo (dBVrms, estimasi FFT)');a.append('</g></svg>');(G/'waveform_dan_fft.svg').write_text(''.join(a))
a=svg_start(1500,1150);text(a,70,70,'Ringkasan hasil uji DTMF — digit 4',36);text(a,70,115,'29 Oktober 2026 | hasil ukur, analisis rekaman, dan replay decoder',22)
lines=[('Hasil website yang dilaporkan','Digit 4 terbaca hanya pada threshold <0,01.'),('WAV yang benar-benar diuji',f'{len(active)/rate*1000:.2f} ms nada aktif; 48 kHz mono; peak 0,8 full scale.'),('Frekuensi dari WAV',f'{wf[0]:.1f} Hz dan {wf[1]:.1f} Hz; twist {wavmetrics["twist_db"]:+.2f} dB.'),('Frekuensi yang dicatat di workbook',f'{v(36):g} Hz dan {v(45):g} Hz; berbeda dari hasil fit CSV/WAV.'),('Gain summer dari FFT workbook',f'Rendah {metrics[2]["value"]:.4f}; tinggi {metrics[3]["value"]:.4f} V/V; nominal 0,4545.'),('Makna threshold yang telah diverifikasi','Skor Goertzel / energi total / jumlah sampel, tanpa satuan.'),('Dampak pengubahan volume','Pengali amplitudo bersama idealnya tidak mengubah skor relatif.'),('Keterbatasan hasil deteksi','Bukan bukti lolos batas error frekuensi, twist, atau decoder standar.'),('Data yang perlu dikonfirmasi','FFT rendah +4,0 vs +3,2 dB; tanda rail negatif; metode ukur resistor.'),('Pengujian berikutnya','Capture 0,5–1 s pada ≥20 kSa/s; simpan threshold tepat dan screenshot.')]
for j,(title,body) in enumerate(lines):
    y=175+j*91;a.append(f'<rect x="55" y="{y-30}" width="1390" height="82" rx="6" fill="{"#f0f4f8" if j%2==0 else "#ffffff"}"/>');text(a,75,y,title,23);text(a,75,y+32,body,21)
a.append('</g></svg>');(G/'ringkasan.svg').write_text(''.join(a))
# PNG conversion, original screenshots retained alongside viewable PNG copies.
from PIL import Image
for p in (D/'Rekaman_Osiloskop').glob('*.bmp'):Image.open(p).save(G/(p.stem+'.png'))
subprocess.run([NODE,str(P/'04_Skrip/render.cjs')],check=True)
manifest={str(p.relative_to(P)):hashlib.sha256(p.read_bytes()).hexdigest() for p in P.rglob('*') if p.is_file() and p.name!='manifest.json' and 'node_modules' not in p.parts}
(P/'manifest.json').write_text(json.dumps(manifest,indent=2))
