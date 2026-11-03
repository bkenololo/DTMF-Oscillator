"""Numerical checks against impedances and known synthetic waveforms."""
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"src"))
from wien import (analyze, frequency_from_crossings, harmonic_fit, make_rows,
                  network_theory, read_raw, resistor_candidates, validate_config,
                  capacitor_value_series)


class PhysicsChecks(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((ROOT/"config.json").read_text())

    def test_matched_frequency(self):
        f, a = network_theory(20680, 20680, 10e-9, 10e-9)
        self.assertAlmostEqual(f, 769.6080420304417, places=9)
        self.assertAlmostEqual(a, 3)

    def test_unequal_network_against_complex_impedances(self):
        r1, r2, c1, c2 = 18000, 24000, 9e-9, 11e-9
        f, gain = network_theory(r1, r2, c1, c2)
        s = 2j*math.pi*f
        z_series = r1+1/(s*c1)
        z_shunt = 1/(1/r2+s*c2)
        beta = z_shunt/(z_series+z_shunt)
        self.assertAlmostEqual(beta.imag, 0, places=12)
        self.assertAlmostEqual(1/beta.real, gain, places=12)

    def test_tolerance_scaling(self):
        f, _ = network_theory(20000, 20000, 10e-9, 10e-9)
        high_c, _ = network_theory(20000, 20000, 11e-9, 11e-9)
        low_c, _ = network_theory(20000, 20000, 9e-9, 9e-9)
        self.assertAlmostEqual(high_c/f, 1/1.1)
        self.assertAlmostEqual(low_c/f, 1/0.9)

    def test_independent_grid_and_deduplication(self):
        validate_config(self.cfg)
        rows = make_rows(self.cfg)
        self.assertEqual(len(rows), 12150)
        self.assertEqual(len({r['case_id'] for r in rows}), 11150)
        for target in [770, 1209]:
            self.assertEqual(len(resistor_candidates(target, self.cfg)), 5)
            for cap in self.cfg['capacitance_nominal_values_f']:
                for tol in [1, 5, 10]:
                    subset = [r for r in rows if r['target_hz'] == target and r['C_nominal_f'] == cap
                              and r['cap_tolerance_percent'] == tol]
                    self.assertEqual(len(subset), 225)
                    self.assertEqual(len({(r['R1_ohm'], r['R2_ohm']) for r in subset}), 25)
                    expected_r={770:[18000,20000,20680,22000,24000],
                                1209:[11000,12000,13000,13150,15000]}[target]
                    self.assertEqual(sorted({r['R1_ohm'] for r in subset}),expected_r)
                    self.assertTrue(any(r['C1_offset_percent'] == -tol and r['C2_offset_percent'] == tol for r in subset))

    def test_capacitor_values_are_preferred(self):
        expected = {6.8:'E12/E24',7.5:'E24',8.2:'E12/E24',9.1:'E24',10:'E12/E24',
                    11:'E24',12:'E12/E24',13:'E24',15:'E12/E24'}
        for cap in self.cfg['capacitance_nominal_values_f']:
            self.assertEqual(capacitor_value_series(cap),expected[round(cap*1e9,5)])

    def test_tolerance_groups_do_not_merge_nominal_capacitors(self):
        from expanded_reporting import tolerance_ranking
        groups=tolerance_ranking(make_rows(self.cfg),self.cfg)
        self.assertEqual(len(groups),1350)
        self.assertTrue(all(r['simulated_grid_points']==9 for r in groups))

    def test_nominal_ranking_does_not_select_lucky_tolerance(self):
        from expanded_reporting import nominal_ranking
        common={'oscillation_status':'settled_oscillation','resistor_count':2,
                'C_nominal_f':1e-8,'R1_ohm':20000,'R2_ohm':20000}
        nominal=dict(common,case_id='nominal',capacitors_nominal=True,simulated_abs_error_percent=0.5)
        lucky=dict(common,case_id='tolerance',capacitors_nominal=False,simulated_abs_error_percent=0.0001)
        self.assertEqual([r['case_id'] for r in nominal_ranking([nominal,lucky])],['nominal'])

    def test_harmonic_measurement_known_signal(self):
        t = np.arange(0, 0.1, 5e-6)
        f = 770.123
        v = 0.023+2*np.sin(2*np.pi*f*t)+0.1*np.sin(6*np.pi*f*t+0.7)
        thd, fundamental, residual, dc = harmonic_fit(t[::4], v[::4], f, 10)
        self.assertAlmostEqual(thd, 5, places=8)
        self.assertAlmostEqual(fundamental, 2, places=8)
        self.assertAlmostEqual(dc, 0.023, places=8)
        self.assertLess(residual, 1e-10)
        measured = frequency_from_crossings(t, v)
        self.assertLess(abs(measured-f)/f, 1e-4)

    def test_decay_not_reported_as_settled_oscillator(self):
        t = np.arange(0, 0.500001, 5e-6)
        v = np.exp(-t/0.01)*np.sin(2*np.pi*770*t)
        result = analyze(t, v, {'target_hz': 770}, self.cfg)
        self.assertEqual(result['oscillation_status'], 'no_sustained_oscillation')
        self.assertIsNone(result['simulated_frequency_hz'])

    def test_binary_parser(self):
        matrix = np.array([[0., 0.], [1e-5, 1.2], [2e-5, -0.3]], dtype=np.float64)
        header = b'Title: test\nFlags: real\nNo. Variables: 2\nNo. Points: 3\nVariables:\n0 time time\n1 v(out) voltage\nBinary:\n'
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'test.raw'
            p.write_bytes(header+matrix.tobytes())
            t, v = read_raw(p)
            np.testing.assert_array_equal(t, matrix[:, 0])
            np.testing.assert_array_equal(v, matrix[:, 1])


if __name__ == '__main__':
    unittest.main()
