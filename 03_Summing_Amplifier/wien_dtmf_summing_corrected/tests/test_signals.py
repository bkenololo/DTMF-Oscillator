"""Independent signal, network, parser and audio checks for the new combined stage."""
from pathlib import Path
import json,sys,tempfile,unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from summing import grid_rows,base_parameters,read_raw_multi,two_tone_fit,write_netlist
from audio_export import lowpass_decimate,decode_basic,write_pcm,read_pcm

class SignalChecks(unittest.TestCase):
    def test_inverting_sum_gain_and_phase_against_known_signals(self):
        t=np.arange(0,.1,1/48000);f=[769.61,1208.87]
        a=3*np.sin(2*np.pi*f[0]*t+.2);b=3.1*np.sin(2*np.pi*f[1]*t-.8)
        output=-10/22*(a+b)
        c,fit=two_tone_fit(t,output,f)
        self.assertLess(np.max(np.abs(fit-output)),1e-11)
        amps=np.hypot(c[1::2],c[2::2]);np.testing.assert_allclose(amps,[3*10/22,3.1*10/22],rtol=1e-12)
    def test_summer_tolerance_gains_against_kcl(self):
        # Virtual ground: (V1/Ra)+(V2/Rb)+(Vo/Rf)=0.
        va,vb,ra,rb,rf=2.1,-.9,22000*.99,22000*1.01,10000*1.01
        vo=-rf*(va/ra+vb/rb)
        self.assertAlmostEqual(va/ra+vb/rb+vo/rf,0,places=15)
    def test_full_factorial_endpoints_and_selected_values(self):
        cfg=json.loads((ROOT/'config.json').read_text());rows=grid_rows(cfg)
        self.assertEqual(len(rows),583)
        for study,count in [('oscillator_R',81),('oscillator_C',81),('summing_R',27)]:
            for tol in (1,5,10):self.assertEqual(sum(r['study']==study and r['tolerance_percent']==tol for r in rows),count)
        p=base_parameters(cfg)
        self.assertEqual(p['parts']['low'],{'R1':[20000,620],'R2':[20000,560]})
        self.assertEqual(p['parts']['high'],{'R1':[13000,82],'R2':[13000,110]})
        self.assertEqual(p['summer_Rf_ohm'],10000);self.assertEqual(p['summer_Rin_low_ohm'],22000)
    def test_multiple_vector_binary_parser_preserves_units(self):
        arr=np.array([[0,0,0,0],[1e-6,1,2,-30/22],[2e-6,2,3,-50/22]],float)
        header=b'Title: known values\nFlags: real\nNo. Variables: 4\nNo. Points: 3\nVariables:\n0 time time\n1 v(low_out) voltage\n2 v(high_out) voltage\n3 v(sum_out) voltage\nBinary:\n'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'trace.raw';p.write_bytes(header+arr.tobytes());x=read_raw_multi(p)
            np.testing.assert_array_equal(x['v(sum_out)'],arr[:,3])
            np.testing.assert_array_equal(x['time'],arr[:,0])
    def test_four_channels_and_physical_series_parts_in_netlist(self):
        cfg=json.loads((ROOT/'config.json').read_text());p=base_parameters(cfg)
        with tempfile.TemporaryDirectory() as d:
            text=write_netlist(p,cfg,Path(d)).read_text()
            self.assertEqual(sum(line.endswith(' TL074') for line in text.splitlines()),4)
            self.assertIn('Rlow_R1_2 low_R1_junction1 low_series_rc 620',text)
            self.assertIn('Rsum_in_low low_out sum_inv 22000',text)
            self.assertIn('Rsum_feedback sum_out sum_inv 10000',text)
            self.assertNotIn('SIN(',text.upper())
    def test_audio_antialias_filter_preserves_passband_and_rejects_alias(self):
        fs=96000;t=np.arange(fs)/fs
        tone=np.sin(2*np.pi*770*t);alias=np.sin(2*np.pi*9000*t)
        y=lowpass_decimate(tone,fs,8000);z=lowpass_decimate(alias,fs,8000)
        yy=y[100:-100];zz=z[100:-100]
        self.assertLess(abs(np.sqrt(np.mean(yy**2))*2**.5-1),.002)
        self.assertLess(np.sqrt(np.mean(zz**2)),.001)
        dc=lowpass_decimate(np.full(fs,.7),fs,8000);np.testing.assert_allclose(dc,.7,atol=1e-12)
    def test_basic_decoder_detects_four_and_rejects_single_tone_and_silence(self):
        fs=8000;t=np.arange(round(.3*fs))/fs
        low=.35*np.sin(2*np.pi*769.61*t);high=.35*np.sin(2*np.pi*1208.87*t)
        self.assertEqual(decode_basic(np.r_[np.zeros(800),low+high,np.zeros(800)],fs)['decoded'],'4')
        self.assertEqual(decode_basic(low,fs)['decoded'],'')
        self.assertEqual(decode_basic(np.zeros(4000),fs)['decoded'],'')
    def test_pcm_round_trip_calibration(self):
        v=np.linspace(-2,2,1000);scale=3
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'known.wav';write_pcm(p,v,48000,scale);fs,x=read_pcm(p)
            self.assertEqual(fs,48000);self.assertLessEqual(np.max(abs(x*scale-v)),scale/32767/2+1e-14)

if __name__=='__main__':unittest.main()
