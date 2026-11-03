# Wien bridge oscillator lookup and simulation

Python controls ngspice in batch mode. No LTspice or graphical circuit editor is required.
This package covers the **two independent oscillators**, targeting 770 Hz and 1209 Hz.
The summing amplifier is the next stage and is deliberately not connected during this sweep.

## Start here

1. Open `results/index.html` in a browser to inspect the completed simulation and charts.
2. Read `results/RESULTS.md` for the main findings and limits.
3. Open `results/simulation_lookup_770Hz.csv` and `results/simulation_lookup_1209Hz.csv`
   for the complete lookup tables. These CSV files are numerical simulation outputs,
   not a spreadsheet workbook; no Excel installation is needed.
4. Use `results/nominal_candidates_*Hz.csv` to compare nominal-capacitor resistor choices.
5. Use `results/tolerance_comparison.csv` to compare each resistor pair over the three
   capacitor tolerance scenarios. This is a sampled grid, not a manufacturing yield estimate.
6. `results/selected_nominal_values.json` stores the closest nominal resistor pair for each
   oscillator. The report also distinguishes balanced alternatives from independently chosen R1/R2.

## Sweep specification

All numeric settings are in `config.json`; the exact executed copy is in `results/config_used.json`.

| Quantity | Specification |
|---|---|
| Topology | Wien bridge; non-inverting TL074 amplifier; diode amplitude stabilization |
| Target frequencies | 770 Hz and 1209 Hz, simulated separately |
| C1 and C2 nominal value | **10 nF**, an E12 and E24 preferred nominal value |
| Primary capacitor tolerance | **±10%**, supplied by the user |
| Additional tolerance scenarios | ±1% and ±5%, requested comparisons |
| Capacitor sampling | Each capacitor independently at −tolerance, nominal, +tolerance |
| R1 | Series Wien resistance, between output and series capacitor C1 |
| R2 | Shunt Wien resistance, from non-inverting input to ground |
| Resistor sampling | E24 values within ±20% of matched ideal R, plus the partner's series combination |
| 770 Hz resistor candidates, each position | 18 kΩ; 20 kΩ; 20 kΩ + 680 Ω; 22 kΩ; 24 kΩ |
| 1209 Hz resistor candidates, each position | 11 kΩ; 12 kΩ; 13 kΩ; 13 kΩ + 150 Ω; 15 kΩ |
| Amplifier ground feedback resistor Rg | 10 kΩ |
| Feedback fixed resistor | 15 kΩ |
| Feedback diode-bypassed resistor | 7.5 kΩ |
| Amplitude-control diodes | Two antiparallel historical NXP 1N4148 models |
| Supplies | +12 V and −12 V, from the partner's design |
| Temperature | 27 °C, an explicitly selected simulation condition |
| External output load | None; only the oscillator's own feedback networks load the output |
| Resistor manufacturing tolerances | Not randomized in this stage; R1 and R2 are design variables |
| Capacitor parasitics | Ideal C elements with tolerance variation; ESR, leakage and board parasitics omitted |

The ±20% resistance search neighborhood is a configurable exploration range, **not** a
resistor tolerance or a lab requirement. No claim is made that the listed values are in stock.
The E12/E24 membership of each nominal resistor is recorded in the tables. The partner's
compound resistances are represented by their two individual series resistors in every netlist.

For each oscillator: 5 R1 choices × 5 R2 choices × 3 C1 values × 3 C2 values
× 3 tolerance scenarios = **675 rows**. Each tolerance scenario has **225 rows per oscillator**.
There are **1,350 rows in total**, corresponding to **1,250 unique physical circuits**.
The capacitor-nominal cases shared by the three tolerance scenarios are simulated once,
then reused. The shared `case_id` identifies this reuse.

## Circuit connections

```text
out ── R1 ── C1 ──┬── wien = TL074 non-inverting input (+)
                   ├── R2 ── ground
                   └── C2 ── ground

out ── 15 kΩ ──┬── 7.5 kΩ ──┬── inv = TL074 inverting input (−)
                ├── diode → ──┤
                └── diode ← ──┘
                              └── 10 kΩ ── ground
```

The diodes bypass **only the 7.5 kΩ section**, matching the written calculations.
`R1` and `R2` never mean the gain-setting feedback resistors in this package.
The `.SUBCKT TL074` order is `(non-inverting, inverting, positive supply,
negative supply, output)`. These are model terminals, **not physical DIP pin numbers**.
One subcircuit instance models one amplifier channel, not all four channels of the TL074.

`circuits/770Hz/circuit.cir` and `circuits/1209Hz/circuit.cir` are standalone examples
using your partner's nominal component values. Each sweep case has its own exact circuit
under `results/cases/<case_id>/circuit.cir`.
`circuits/selected_770Hz/circuit.cir` and `circuits/selected_1209Hz/circuit.cir` use
the closest nominal pairs found by the independent sweep. These may have unequal R1/R2.

## Analytical lookup equations

The series and shunt impedances are

```text
Zseries = R1 + 1/(s C1)
Zshunt  = R2/(1 + s R2 C2)
beta(s) = Zshunt/(Zseries + Zshunt)
        = s R2 C1 / [1 + s(R1 C1 + R2 C2 + R2 C1) + s² R1 R2 C1 C2]
```

Setting the imaginary part of the denominator of `1/beta(jω)` to zero gives

```text
f_zero_phase = 1 / [2π sqrt(R1 R2 C1 C2)]
A_required   = 1 + R1/R2 + C2/C1
```

For R1=R2=R and C1=C2=C, these reduce to `f=1/(2πRC)` and `A_required=3`.
These equations assume an unloaded RC network and an ideal, zero-phase non-inverting amplifier.
They predict the RC network zero-phase condition, **not the exact nonlinear oscillation frequency**.
The TL074 model, feedback diodes, gain, and finite amplifier phase are evaluated by ngspice.

The small-signal gain, with the diodes nearly off, is
`1+(15k+7.5k)/10k = 3.25`. The limiting approximation with 7.5k bypassed gives
`1+15k/10k = 2.5`. The analytical column `theory_gain_control_brackets_required`
only checks whether the required gain is between these bounds. It is not simulation proof.
Mismatched R1/R2 or C1/C2 changes both frequency and required gain, so some cases do not oscillate.

## Measurement and classification

- Each transient lasts **0.5 s**, with a maximum timestep of **5 µs**.
- A finite **100 nA startup current pulse** is injected at the non-inverting node at the
  beginning of the run. It returns to zero after 12 µs. There is no sinusoidal drive source.
  This tests response to a documented startup disturbance; it is not a transistor-noise startup model.
- The final **0.1 s** is analyzed after the startup transient.
- Frequency is measured using interpolated positive-going zero crossings around the tail mean.
- An output below **0.1 Vpp** is classified `no_sustained_oscillation` within the simulated duration.
- Tail peak-to-peak change between two 50 ms windows must be ≤**2%** to be labeled
  `settled_oscillation`. Otherwise it is `not_settled_within_run`.
- The amplitude and settling thresholds above are **analysis settings**, not lab acceptance limits.
- THD uses a least-squares fit of the measured fundamental and harmonics 2 through 10:
  `THD = sqrt(V2²+...+V10²)/V1`. It is reported in percent only for settled signals.
  A separate fit residual is retained. This finite-harmonic estimate is not total noise-plus-distortion.
- DC offset of settled signals is the fitted constant term. For nonsettled signals it is the
  raw mean over the analysis window.
- The plotted spectrum is a Hann-window FFT; the 0.1 s window gives **10 Hz bin spacing**.
  The more precise tabulated frequency comes from zero-crossing interpolation, not an FFT-bin label.
- Settling time is estimated from 10 ms peak-to-peak windows and is approximate.
- Closest nominal finalists are rerun at **2.5 µs** maximum timestep for a numerical convergence check.
- All simulation failures remain explicit; missing values are not replaced with zeros.

No frequency-error, THD, amplitude, or decoder pass limit has been invented for the lab.
A 3×3 deterministic capacitor grid does not prove behavior at every intermediate tolerance value.
This stage omits supply tolerances, temperature sweeps, resistor manufacturing tolerances,
load sweeps, board parasitics, and model-to-hardware uncertainty.

## Run again

Python 3.10 or later is required. The package includes a locally compiled **ngspice 47
for macOS arm64**, linked only to macOS system libraries. It does not require Homebrew.
The runner locates it automatically and explicitly loads its POLY support library.
On another operating system or architecture, install ngspice with XSPICE/POLY support
and pass its executable path, or build using the included source archive.

From a terminal in this folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

Useful commands:

```sh
# Generate analytical lookup tables only, without running ngspice.
.venv/bin/python run.py --theory-only

# Rerun the complete sweep and disregard cached measurements.
.venv/bin/python run.py --force

# Select another ngspice executable.
.venv/bin/python run.py --ngspice /absolute/path/to/ngspice

# Use fewer simultaneous simulator processes.
.venv/bin/python run.py --workers 2

# Run the independent physics and measurement checks.
.venv/bin/python -m unittest discover -s tests -v

# Validate coverage, source-model hashes, and completed case evidence.
.venv/bin/python scripts/validate_results.py

# Regenerate charts from existing CSVs without simulating again.
.venv/bin/python scripts/render_plots.py
```

Successful cases are cached with a fingerprint of configuration, source code, model files,
physical component values, and simulator version. Changing these inputs causes recomputation.
Existing tables and charts are regenerated. Per-case netlists, logs, and metrics are preserved;
large temporary raw files are removed after analysis. Representative traces are stored as
portable CSV excerpts and compressed NumPy arrays.

For a small setup test, use `--limit 4 --results /path/to/separate/smoke_folder --no-plots`.
`--limit` is explicitly marked incomplete and does not replace a full sweep.

To rebuild the bundled simulator locally, run `sh scripts/build_ngspice.sh`.
This requires a C/C++ compiler and make. It does not install system-wide software.

## Sources and model provenance

- `models/TL074.301`: exact user-supplied file, including original line endings and EOF marker.
- `models/TL074_ngspice.lib`: same model with CRLF normalized and the trailing DOS `0x1a`
  marker removed. No device parameters or circuit equations were changed.
- The model header describes a ±15 V reference supply. This project uses the requested design's
  ±12 V supply. The model can be simulated at that setting; this does not establish datasheet
  accuracy at ±12 V or across device/process/temperature variation.
- `models/1N4148.lib`: historical NXP manufacturer model preserved in the PySpice library:
  https://github.com/FabriceSalvaire/PySpice/blob/master/examples/libraries/diode/switching/1N4148.lib
  The original NXP URL is retained in the file. Supplier download was unavailable; the model
  is not falsely represented as a newly downloaded current Nexperia model.
- Model hashes and normalization details: `models/provenance.json`.
- Preferred resistor values: https://www.vishay.com/docs/31001/dectable.pdf
- Wien-bridge background: https://www.ti.com/lit/an/sloa060/sloa060.pdf
- ngspice manual and POLY/XSPICE support: https://ngspice.sourceforge.io/docs.html
- Official ngspice source release:
  https://sourceforge.net/projects/ngspice/files/ng-spice-rework/47/ngspice-47.tar.gz/download
- Simulator source archive and license: `vendor/`; reproducible build command:
  `scripts/build_ngspice.sh`.

## Folder contents

```text
run.py, config.json, requirements.txt   entry point and editable specification
src/                                  simulation, equations, analysis, reporting
models/                               original and ngspice-ready component models
circuits/                             two nominal oscillator netlists
tests/                                independent physics and measurement checks
scripts/                              simulator build helper
vendor/                               ngspice source archive and license
tools/ngspice/                        local macOS arm64 simulator
results/                              lookup CSVs, report, charts, case evidence, traces
```

## Common reproduction launcher

See [the Oscillator reproduction instructions](../../README.md) for Python setup, ordered stages, run logs and LTspice regeneration. Run `python reproduce.py --list` from the top-level Oscillator folder. Existing local commands in this README remain usable.
