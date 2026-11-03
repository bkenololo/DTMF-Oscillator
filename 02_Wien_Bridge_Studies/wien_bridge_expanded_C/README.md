# Expanded Wien bridge capacitor sweep

The new sweep tests **nine standard nominal capacitor values**, each with independent
capacitor tolerance offsets. The previous `wien_bridge_lookup` folder is preserved.
The same TL074 model, diodes, circuit connections, supplies, and measurement method are used.

## Open the results

- **START_HERE.html** or **SUMMARY.md**: combined overview and closest nominal selections.
- `results/index.html`: requested broad capacitor sweep, tables, and plots.
- `results/best_per_nominal_C_*Hz.csv`: closest settled resistor pair at every nominal C.
- `results/simulation_lookup_*Hz.csv`: complete broad sweep, including failures to oscillate or settle.
- `results/tolerance_comparison.csv`: tolerance results grouped separately by nominal C and R1/R2.
- `refinement/results/`: separate, finer E24 series-resistor sweep at nominal 10 nF.
- `selected_nominal_values.json` and `circuits/recommended_*Hz/circuit.cir`: closest
  nominal-frequency choices across both completed searches.

## Requested broad sweep

| Quantity | Values |
|---|---|
| Targets | 770 Hz and 1209 Hz, independent oscillators |
| Common nominal C1 and C2 | 6.8, 7.5, 8.2, 9.1, 10, 11, 12, 13, 15 nF |
| Preferred series | All E24; 6.8, 8.2, 10, 12, 15 nF are also E12 |
| Tolerance at every nominal C | ±1%, ±5%, ±10%; ±10% is the primary scenario |
| Actual capacitor offsets | Each capacitor independently at lower limit, nominal, upper limit |
| 770 Hz R1/R2 choices | 18 kΩ, 20 kΩ, 20 kΩ+680 Ω, 22 kΩ, 24 kΩ |
| 1209 Hz R1/R2 choices | 11 kΩ, 12 kΩ, 13 kΩ, 13 kΩ+150 Ω, 15 kΩ |

For example, nominal **8.2 nF ±10%** uses actual values **7.38, 8.2, 9.02 nF**
independently for C1 and C2. Tolerance values need not themselves be E-series nominal parts.
Arbitrary unequal *nominal* C1/C2 combinations are not included: they share a nominal
value at each step, with independent actual deviations.

R1 means the series Wien resistance; R2 means the shunt Wien resistance. Both are swept
independently. The resistor grids stay fixed as nominal C changes. In `config.json`,
`resistor_reference_capacitance_f=1e-8` preserves the original resistor neighborhood;
`capacitance_nominal_values_f` specifies the actual capacitor sweep. The legacy scalar
`capacitance_nominal_f` remains for compatibility.

```text
9 nominal C × 5 R1 × 5 R2 × 3 C1 offsets × 3 C2 offsets × 3 tolerances
= 6,075 rows per oscillator; 12,150 rows overall.
```

Equivalent physical circuits are simulated once and reused across scenario rows. Matching
uses the same 14 significant digits written to SPICE. The broad sweep has **11,150 distinct
physical circuits**. Each nominal-C/tolerance combination has **225 rows per oscillator**.

## Separate resistor refinement

The broad nominal-C search alone did not improve the 770 Hz match within the retained
resistor grid. A separate search therefore tests neighboring E24 resistors in the series
combinations already present in the circuit. This is kept separate from the requested
unchanged-resistor broad sweep.

| Target | Base resistor | Additional series resistor choices in each R position |
|---|---:|---|
| 770 Hz | 20 kΩ | 510, 560, 620, 680, 750 Ω |
| 1209 Hz | 13 kΩ | 82, 91, 100, 110, 150 Ω |

Both capacitors have nominal value 10 nF in this additional search. All three tolerance
scenarios and independent capacitor offsets are retained: **1,350 rows**, **1,250 physical
circuits**. Its configuration and outputs are under `refinement/`.
`run_refinement.py` changes only the candidate generator and calls the same simulation engine.

## Circuit and analysis retained

- Supplied TL074.301 model and the same documented text normalization.
- Historical NXP 1N4148 diode model, antiparallel across only the 7.5 kΩ feedback section.
- Amplifier feedback: 10 kΩ to ground, 15 kΩ fixed, 7.5 kΩ diode-bypassed.
- ±12 V supplies, 27 °C, no external output load or summing amplifier.
- Same finite 100 nA startup pulse, ending at 12 µs; no sine-wave drive source.
- Same 0.5 s transient, maximum timestep 5 µs, final analysis interval 0.1 s.
- Same interpolated positive-going crossings for frequency and least-squares harmonic
  fit for THD using harmonics 2–10. No smoothing or denoising.
- Same settled classification: at least 0.1 Vpp and final-window Vpp change ≤2%.
- Same Hann-window FFT, 10 Hz bin spacing, normalized to its largest peak.
- Closest nominal candidates rerun with maximum timestep 2.5 µs for comparison.

The thresholds classify simulation results; they are not lab acceptance limits. For a
nonsettled row, amplitude/DC columns describe the analysis interval, not a proven steady state.
The nominal ranking uses nominal capacitors, not favorable tolerance offsets. Smallest
frequency error is not automatically lowest distortion; both are reported.

```text
Zseries = R1 + 1/(s C1)
Zshunt = R2/(1+s R2 C2)
f_zero_phase = 1/[2π sqrt(R1 R2 C1 C2)]
A_required = 1 + R1/R2 + C2/C1
```

These are ideal unloaded network equations. The nonlinear simulated oscillator can
differ because of the amplifier and diode behavior. The grids are deterministic samples,
not statistical yield estimates or guarantees over every intermediate tolerance point.
Capacitor parasitics, resistor manufacturing tolerances, board wiring, temperature/supply
variation, and summer loading are outside this stage. Hardware may still need trimming.

## Run without LTspice

The bundled local simulator is **ngspice 47 for macOS arm64**. On another platform,
install ngspice with POLY/XSPICE support and pass `--ngspice /absolute/path/to/ngspice`.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
.venv/bin/python run_refinement.py
.venv/bin/python scripts/verify_finalists.py
.venv/bin/python scripts/combine_results.py

.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/validate_results.py
.venv/bin/python scripts/validate_results.py --results refinement/results

.venv/bin/python scripts/render_plots.py
.venv/bin/python scripts/render_plots.py --results refinement/results
```

Broad run: eight concurrent simulators. Refinement: two. Override with `--workers 2`
or another suitable count. Successful cases are cached; `--force` reruns them.
`--theory-only` produces analytical tables. A setup test can use
`--limit 4 --results /path/to/test_folder --no-plots`; it is marked incomplete.

The small launcher `tools/ngspice/bin/ngspice` caches only the unchanged version banner.
Every actual simulation executes the unchanged `ngspice-real` binary. Its hash is recorded
in `reference/simulator_launcher.json`. This avoids loading libraries for repeated version
queries and changes no circuit or numerical settings. The original source archive and local
build helper remain under `vendor/` and `scripts/`.

`scripts/verify_finalists.py` compares the five closest nominal candidates per target
from both grids at **1.25 µs**, then checks the selected candidates at **0.625 µs**.
This checks numerical differences between close frequency matches. These results, traces,
and the selected candidates' original 5 µs tolerance comparisons are under `verification/`.
The main grids remain at 5 µs for comparison with the previous project.

## Sources and provenance

`src/wien.py` contains the existing circuit generator and measurements, with expanded
candidate generation. `src/expanded_reporting.py` handles multiple nominal C values.
`src/reporting.py` retains original trace capture and timestep checks. `models/` contains
the unchanged models; `reference/` retains previous selections/configuration and checks
that circuit and measurement functions are unchanged. `circuits/` contains inspectable
netlists for every nominal-C winner and final selections. Every simulated case also retains
its netlist, logs, and measured metrics.

Model hashes and source URLs: `models/provenance.json`. Circuit/configuration comparison:
`reference/physics_unchanged.json`. The TL074 header specifies a ±15 V reference supply;
±12 V is retained from the design. Simulation does not establish hardware-model accuracy.

- Preferred values: https://www.vishay.com/docs/31001/dectable.pdf
- Wien bridge background: https://www.ti.com/lit/an/sloa060/sloa060.pdf
- ngspice: https://ngspice.sourceforge.io/docs.html
- Historical NXP diode model mirror:
  https://github.com/FabriceSalvaire/PySpice/blob/master/examples/libraries/diode/switching/1N4148.lib

## Common reproduction launcher

See [the Oscillator reproduction instructions](../../README.md) for Python setup, ordered stages, run logs and LTspice regeneration. Run `python reproduce.py --list` from the top-level Oscillator folder. Existing local commands in this README remain usable.
