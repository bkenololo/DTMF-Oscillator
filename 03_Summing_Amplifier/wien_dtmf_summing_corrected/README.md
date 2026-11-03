# Corrected component choice: Wien oscillators + TL074 summing amplifier

Start with `SUMMARY.md` or `START_HERE.html` for results. For a DTMF decoder that accepts audio files, open **`audio/dtmf_4_steady_48k.wav`**. The intended digit is **4**. The repeated file should give **444**. These files contain the output of the simulated circuit, not regenerated ideal sine waves.

## Circuit and design inputs

The component choice is pinned to the user's refinement table: high-oscillator R1=13,082 Ω and R2=13,110 Ω. These values supersede the earlier summing folder's 13.1 kΩ / 13.1 kΩ pair. No timestep check is allowed to reselect components. The user's oscillator values take precedence over the older values in the partner calculation. The summer values come directly from the supplied `Perhitungan.docx`.

| Block | Values |
|---|---|
| Low oscillator, nominal target 770 Hz | Series Wien R1=20 kΩ+620 Ω; shunt Wien R2=20 kΩ+560 Ω; C1=C2=10 nF |
| High oscillator, nominal target 1209 Hz | R1=13 kΩ+82 Ω; R2=13 kΩ+110 Ω; C1=C2=10 nF |
| Each oscillator gain control | Rg=10 kΩ; feedback 15 kΩ+7.5 kΩ; antiparallel 1N4148 across only the 7.5 kΩ part |
| Summer | Each Rin=22 kΩ; Rf=10 kΩ; non-inverting input at ground |
| Fourth channel | Non-inverting input at ground; output connected to inverting input |
| Supply and temperature | ±12 V, 27 °C, as in the preceding simulations |
| Nominal external load | Pure 1 MΩ resistor, representing the selected high-impedance scope setting |
| Supply bypass | 100 nF and 10 µF from each ideal rail to ground, from the partner BOM |

The summing node is approximately at virtual ground. Applying Kirchhoff's current law gives

`Vout ≈ −Rf × (Vlow/Rin_low + Vhigh/Rin_high)`.

Thus each nominal tone has gain **−10/22 = −0.454545**, and the summer noise gain is **1 + 10/22 + 10/22 = 1.90909**. Connecting the summer also loads each oscillator with approximately 22 kΩ. Both oscillators are simulated together with this real loading; their previously chosen component values are retained without further retuning.

The original supplied `TL074.301`, its normalized ngspice library, the 1N4148 model, local simulator/runtime, license and simulator-build source were copied from `wien_bridge_expanded_C`. Hash checks are in `reference/copied_auxiliary_hashes.json`. The model subcircuit terminal order is **(+ input, − input, V+, V−, output)**, not the physical DIP pin numbering.

## Tests and scope

- Nominal: 0.5 s transient, maximum timestep 1.25 µs, then a 0.625 µs numerical check.
- Load comparison: 1 MΩ nominal, 10 MΩ, no external load, and a clearly labelled 10 kΩ stress load. A 50 Ω termination is not part of this design.
- Oscillator resistor tolerance: all four effective Wien resistances independently take −tolerance / nominal / +tolerance, for ±1%, ±5%, ±10% scenarios. This gives 81 rows per scenario. Each effective resistance's two physical series parts move together by the same percentage in this grid; the netlist retains both actual parts. Internal opposite-sign part errors are not a separate dimension here. For ideal series resistors, they produce intermediate effective totals within the same bounds, as tested in the previous individual-oscillator study.
- Capacitor tolerance: all four 10 nF capacitors independently take the same three levels, 81 rows per ±1%, ±5%, ±10% scenario.
- Summing resistor tolerance: both 22 kΩ inputs and the 10 kΩ feedback resistor independently take the three levels, 27 rows per ±1%, ±5%, ±10% scenario.
- Combined stress: 16 selected corners combine ±1% oscillator resistors with ±10% capacitors. Each oscillator's R1/R2 move together, and its C1/C2 move together. This is a limited joint stress study, not the full Cartesian product of every component tolerance.

Each separate tolerance study holds the other component groups at nominal values. The tolerance grids use the earlier 5 µs maximum timestep for practical runtime. They are compared at their own common nominal grid point; the final nominal report and WAV files use 1.25 µs. No lab frequency, distortion, twist or decoder pass limits were supplied, so these metrics are reported without inventing pass/fail limits.

The partner BOM specifies **1% metal-film resistors**, used as the primary resistor scenario and purchase specification for the refined resistor values. The user's earlier **10% capacitor tolerance** is retained as the primary capacitor scenario. The other scenarios are comparisons. E24/E12 identify preferred nominal values; the purchased part determines its actual tolerance.

## Timestep comparison without changing components

The user's standalone table was generated at 5 µs maximum timestep (769.583749 Hz and 1209.097838 Hz). Like the previous summing workflow, the final nominal waveform and WAV use 1.25 µs, with a 0.625 µs numerical check. A separate 5 µs connected-circuit run is included, and both standalone oscillators are rerun at 5 µs and 1.25 µs. `results/timestep_and_loading_comparison.csv` compares matching timesteps. Thus a frequency difference between table and nominal WAV is explicitly separated into numerical-timestep effects and loading; it is never addressed by swapping resistor choices.

## Measurement definitions

- Each oscillator: original zero-crossing frequency measurement, settled-waveform check, Vpp, harmonics 2–10 THD, and settling estimate. The final 0.1 s is the measurement interval. Settled means Vpp>0.1 V and less than 2% Vpp change between the final two 50 ms intervals. These are analysis settings, not lab acceptance limits.
- Summer gain: two-tone sinusoidal fits at the measured oscillator frequencies, comparing each output fundamental with its corresponding input fundamental. Phase near 180° shows inversion.
- Twist: `20 log10(high-tone fundamental amplitude / low-tone fundamental amplitude)`.
- The RMS residual to two fitted fundamentals includes the oscillators' existing distortion. It is not single-tone THD.
- `output_harmonics_2_to_10_relative_combined_fundamentals_percent` fits the two fundamental families and harmonics 2–10 simultaneously, normalized by the root-sum-square of the two fundamental amplitudes. It is explicitly a two-tone harmonic-content metric.
- Summing error compares the actual output with the instantaneous ideal weighted sum of the actual oscillator outputs. Its AC RMS includes finite-gain/phase error; it does not measure only nonlinear distortion.
- The separately fitted selected mixing products are |fH−fL|, fH+fL, |2fL−fH|, 2fL+fH, |2fH−fL|, 2fH+fL. Very small values are numerical/model results, not a demonstrated physical noise or intermodulation floor.
- FFTs use uniformly interpolated data from the final 0.1 s, a Hann window and 10 Hz bin spacing. Magnitude is relative to the larger fitted output fundamental. No spectrum smoothing is applied. The simulated transient has no injected noise; the plotted floor is not measured hardware noise.

## WAV files and decoder testing

`audio/` contains mono, 16-bit PCM files at 48 kHz and 8 kHz:

- `dtmf_4_steady_48k.wav`: recommended first test. Actual output from 0.2–0.5 s, with 0.1 s digital silence before and after.
- `dtmf_4_repeated_48k.wav`: repeats that measured segment three times, separated by 0.15 s silence. Intended result: 444.
- `dtmf_4_startup_48k.wav`: full simulated 0.5 s, including oscillator startup.
- The corresponding `_8k.wav` files support decoders expecting 8 kHz audio.

The export linearly interpolates the adaptive SPICE trace to a 960 kHz intermediate grid, applies an explicitly defined linear-phase antialias FIR, and decimates to the output rate. The FIR is Kaiser-windowed sinc (beta=8.6), 48 taps per decimation factor plus one, cutoff 0.45 times the final sample rate. The 8 kHz version has a narrower bandwidth and consequently attenuates more high harmonics. One common linear scale maps the nominal output peak to approximately 0.8 PCM full scale; the original relative tone amplitudes are preserved. There is no sine regeneration or selective harmonic suppression. `audio_metadata.json` records the voltage calibration, filtering and exact source intervals. Digital silence/repetition are file-format conveniences, not circuit switching simulations.

The included basic spectral checker identifies nominal audio as 4 and repeated audio as 444. It uses declared frame, dominance and amplitude settings. It is a reproducible sanity check, not a standards-compliant receiver or a test of the user's particular hardware/software decoder. Decoder-specific input limits and interface circuitry remain unspecified. WAV amplitude is a digital scale; physical line/headphone voltage depends on playback hardware.

## Files

- `circuits/nominal/circuit.cir`: portable nominal netlist referencing the included models.
- `results/cases/<case_id>/`: exact simulated netlists, startup configuration, simulator console/log and metrics. The nominal case also retains native ngspice `waveform.raw`.
- `waveforms/nominal_native.csv`: native time, low oscillator voltage, high oscillator voltage and summed output voltage, in seconds/volts.
- `waveforms/nominal_fft.csv`: output FFT in Hz, volts peak and dB relative to the larger fundamental.
- `results/tolerance_*.csv`: all scenario rows with actual physical part values, case identifiers and measured results.
- `results/tolerance_summary.csv`: sampled ranges by study and tolerance; these are deterministic samples, not yields or continuous-domain guarantees.
- `results/numerical_and_load_checks.csv`, `validation.json`: numerical and load checks, source/model hashes and coverage.
- `reference/`: partner calculation, extracted text, copied final choices and provenance.
- `figures/`: waveform, linearity, spectra and tolerance plots.

## Reproduce

The included simulator is the same local macOS ARM64 ngspice 47 runtime used previously. On other platforms set `NGSPICE` to an installed executable, or adapt/run `scripts/build_ngspice.sh` using the included source archive.

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 run.py
python3 scripts/check_standalone.py
python3 scripts/export_audio.py
python3 scripts/make_report.py
python3 -m unittest discover -s tests -v
python3 scripts/decode_wav.py audio/dtmf_4_steady_48k.wav
```

`python3 run.py --nominal` runs just the nominal circuit. Completed cases are cached by parameters, settings, measurement source and model hashes. `--workers 4` changes concurrency. Sources are complete; no LTspice GUI is needed.

## Limits and physical implementation

The supplied historical TL074 macromodel is retained at ±12 V, even though its header references ±15 V characterization. Four single-channel model instances share ideal rails; common-package crosstalk, shared supply impedance, PCB/breadboard parasitics, real probe capacitance, capacitor ESR/leakage, thermal drift and component noise are not characterized here. Scope input capacitance is an open parameter (`scope_input_capacitance_f: null`), not an assumed hardware specification. Gain-control resistor and diode manufacturing variations are outside these sweeps.

Use high-impedance oscilloscope input for the intended measurement. Keep the fourth channel's inputs defined as in the netlist. Fit the supply decoupling capacitors when building the circuit; the negative-rail electrolytic's positive lead goes to ground. The capacitor model is unpolarized in SPICE. Hardware may require frequency trimming even when the nominal model closely matches the target.

## Common reproduction launcher

See [the Oscillator reproduction instructions](../../README.md) for Python setup, ordered stages, run logs and LTspice regeneration. Run `python reproduce.py --list` from the top-level Oscillator folder. Existing local commands in this README remain usable.
