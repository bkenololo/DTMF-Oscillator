# Resistor tolerance update for the final chosen oscillators

This update varies only the four physical frequency-setting resistors. It uses the existing TL074 and diode models, gain-control circuit, startup pulse, ±12 V supplies, 27 °C temperature, and 0.5 s transient. C1 and C2 remain exactly 10 nF. Gain-setting resistors are held at their original values. Capacitor and resistor tolerances are not combined in this update.

| Target | R1 physical parts | R2 physical parts |
|---|---|---|
| 770 Hz | 20 kΩ + 620 Ω | 20 kΩ + 560 Ω |
| 1209 Hz | 13 kΩ + 100 Ω | 13 kΩ + 100 Ω |

## Tolerance scenarios

All nominal physical resistor values belong to E24. Some also belong to E12. E24 is conventionally associated with ±5% parts and E12 with ±10% parts; the actual tolerance is specified by the purchased component, not forced by membership in a preferred-value series. No resistor manufacturer or part number was supplied. Consequently ±1%, ±5%, and ±10% are explicitly separate scenarios, applied uniformly to all four physical frequency-setting resistors. Use the scenario matching the parts purchased; ±1% is included for precision parts at the same nominal values.

For each scenario every physical resistor independently takes its lower endpoint, nominal value, or upper endpoint. This gives 3^4 = 81 rows per target and tolerance, 243 rows per target and 486 total. The nominal physical circuit is shared across three scenarios, giving 482 unique transient simulations. Each row lists every part's actual resistance and offset, total R1/R2, measured frequency, amplitude, distortion, and oscillation status.

The effective series resistance is the sum of actual part values. Its fractional error is the nominal-resistance-weighted average of the two part errors. When both physical parts share a tolerance t, the total's endpoints are exactly ±t. Opposite signs within a pair create additional interior values; they are simulated in the full CSV. These are deterministic samples, not a distribution, yield estimate, or proof over a continuous tolerance interval.

## Files and plots

- `figures/resistor_tolerance_770Hz.png` and `figures/resistor_tolerance_1209Hz.png`: three tolerance panels. Each panel shows the nine coherent cases in which both physical resistors within R1 share the same offset, and similarly within R2. R1 and R2 independently take lower/nominal/upper values. Numbers show simulated frequency in Hz and signed error from the target. Gold marks nominal. Gray marks a case without a settled oscillation.
- `figures/resistor_tolerance_frequency_ranges.png`: minimum/maximum frequency among all settled samples in each 81-row group. The labels state how many of the 81 samples settled. Dark dots show nominal frequency; the dashed line shows the target.
- `resistor_tolerance_770Hz.csv`, `resistor_tolerance_1209Hz.csv`: all component-level tolerance combinations, including internal mismatch within each series pair.
- `resistor_tolerance_summary.csv`: sampled frequency, amplitude and THD ranges, plus settled/nonsettled counts.
- `cases/`: actual netlists, simulator logs and measured metrics. Existing project models are referenced using relative paths.
- `validation.json`: simulation counts, model/source hashes and validation results.
- `run_resistor_tolerance.py`, `config_used.json`, `progress.log`: reproducible source, settings and run record.

The maximum transient timestep is 1.25 µs, matching the final selection verification. Frequency uses interpolated positive zero crossings in the final 0.1 s. Settling and THD use the original measurement code. Results classified as nonsettled are retained in CSV and not included in settled-frequency ranges. The circuit and models are unchanged. All four physical resistor values written into each unique netlist are checked against its scenario row. Nominal frequency must reproduce the final selected frequency within 1 µHz.

## Installing only this update

The update ZIP contains only `resistor_tolerance/`. Extract it into the existing `wien_bridge_expanded_C/` folder. No earlier files need replacing. Run from that project folder:

```sh
python3 resistor_tolerance/run_resistor_tolerance.py
```

Use the Python environment and simulator configured for the existing project. The plotting source needs NumPy and Matplotlib. Completed simulations are cached, so rerunning generates the tables and plots without repeating unchanged circuit runs.
