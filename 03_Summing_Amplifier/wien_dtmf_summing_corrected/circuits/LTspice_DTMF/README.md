# LTspice Wien-bridge DTMF digit 4

Open **DTMF4.asc** for the complete circuit.
Keep all `.asc`, `.asy`, `.lib`, and `.inc` files together in this directory.
The project uses local symbols and models; no global library installation is needed.

## Schematics and matching symbols

| Function | Editable circuit | Reusable hierarchy symbol | Standalone simulation |
|---|---|---|---|
| Low oscillator | LowOscillator.asc | LowOscillator.asy | Test_LowOscillator.asc |
| High oscillator | HighOscillator.asc | HighOscillator.asy | Test_HighOscillator.asc |
| Inverting summer | SummingAmplifier.asc | SummingAmplifier.asy | Test_SummingAmplifier.asc |
| Complete DTMF 4 | DTMF4.asc | Uses all three symbols above | Run DTMF4.asc |

The three block sheets are intentionally free of supply voltage sources, external loads,
and analysis commands. Run their Test_*.asc sheets to simulate each block by itself.
Open a child circuit directly, or use LTspice's hierarchy/open-sheet command on its block.
Editing a child `.asc` updates the corresponding block in the full circuit.
If you move a block into another project, copy its child `.asc`, matching `.asy`, local
primitive symbols, and model files too. Keep the block's filename and port names paired
with its symbol. Avoid adding a Prefix/Value override to a hierarchical BLOCK symbol.

## Values carried over from the final refined design

- Low: series resistance 20k + 620 = 20.620k; shunt resistance 20k + 560 = 20.560k.
- High: series resistance 13k + 82 = 13.082k; shunt resistance 13k + 110 = 13.110k.
- Both oscillators: two 10n capacitors; Rg = 10k; fixed feedback = 15k;
  bypassed feedback = 7.5k. Two antiparallel 1N4148 diodes bypass only the 7.5k resistor.
- The simulated 110-ohm element represents the equivalent of the two parallel 220-ohm
  resistors used in the physical implementation. It retains the original simulation topology.
- Summer: two 22k input resistors and 10k feedback; gain per input = -10/22 V/V.
- Full circuit: +/-12 V, 27 C, 1Meg output scope load, 0.5 s transient,
  maximum time step 1.25u, shared 100n and 10u decoupling on each rail.
- Negative-rail electrolytic: positive to ground, negative to VEE (-12 V).
- U1A/U1B/U1C/U1D are four channels of one TL074. The fourth channel is a grounded
  voltage follower with no external load. VCC is physical pin 4; VEE is physical pin 11.
- Low channel: OUT 1 / IN- 2 / IN+ 3. High: OUT 7 / IN- 6 / IN+ 5.
  Summer: OUT 8 / IN- 9 / IN+ 10. Unused: OUT 14 / IN- 13 / IN+ 12.
- Resistors use American zigzag symbols.

Startup current pulses are simulation-only devices, retained from the original ngspice
circuit. They are written explicitly as Iseed directives beneath the oscillator drawings;
they are not components to build on the breadboard.

The summer-only test uses two **synthetic 3 V peak sine sources** at 770 and 1209 Hz.
Those sources isolate the summer test; they are not substitutes for the oscillators in DTMF4.asc.

## Models

TL074_original.301 is the supplied model preserved byte-for-byte.
TL074.lib contains the same model with the legacy DOS EOF control character removed and
line endings normalized; no circuit equations or device parameters were changed.
1N4148.lib is the same supplied NXP subcircuit used in the corrected ngspice project.
models.inc includes these active libraries. The TL074 model's five pin positions mean
(IN+, IN-, VCC, VEE, OUT); they are not the physical DIP-14 numbering.

## Verification and its scope

The actual ASC wire coordinates and ASY pin definitions were parsed, the hierarchy was
flattened, and an exact graph-isomorphism check compared all 38 elements against the
corrected source circuit. The graph comparison permits arbitrary internal node names
and equivalent resistor/capacitor terminal order, while preserving op-amp and diode pin
order. Port names match the symbols; no pin is disconnected and no named nets are shorted.

LTspice 17.2.4 for macOS then successfully simulated all four *_extracted.cir netlists.
At 0.4-0.5 s, the complete DTMF circuit produced:

| Quantity | LTspice result |
|---|---:|
| Low frequency | 769.612 Hz |
| High frequency | 1209.21 Hz |
| Low oscillator Vpp | 6.06231 V |
| High oscillator Vpp | 6.14397 V |
| DTMF output Vpp | 5.54825 V |

The low/high standalone test benches produced 769.617 Hz / 1209.22 Hz with a 1Meg load.
The summer-only test produced 5.45426 Vpp with its synthetic 3 V peak inputs.
LTspice used source stepping to obtain the oscillator operating points, then completed
all transient runs successfully. This is recorded in the included logs.

The installed Mac version does not export schematic netlists through its batch CLI.
Consequently, simulation verification used our ASC/ASY-extracted netlists, rather than a
netlist exported by the LTspice GUI. Opening/rendering and hierarchy traversal in the
LTspice GUI have not been verified. The PNG previews were rendered directly from the
ASC/ASY drawing geometry and are **not LTspice screenshots**.

The extracted netlists are also supplied as a batch-simulation fallback. After editing
an ASC, regenerate its netlist in LTspice before using the fallback; the supplied CIR
files are snapshots and do not update automatically.

verification/ contains the connectivity report, readable LTspice simulation logs,
and previews of the full circuit and each child block.

## Design reference

Original electrical source: wien_dtmf_summing_corrected/circuits/nominal/circuit.cir.
LTspice file/hierarchy conventions were checked against the installed application's
symbols/help and Analog Devices' schematic reference:
https://analogdevicesinc.github.io/ltspice-reference/ai_ref/SCHEMATIC-REFERENCE.html

## Rebuild this project with Python

From this `LTspice_DTMF` directory, using Python 3.10+:

```bash
python -m pip install -r scripts/requirements.txt
python scripts/reproduce.py
python scripts/reproduce.py --simulate
```

The first command installs Pillow for source-geometry PNG previews. The build and connectivity check do not require a simulator. `--simulate` requires native LTspice; use `--ltspice /path/to/executable` or environment variable `LTSPICE` if it is not autodiscovered. Each native run has a default 120-second timeout, configurable with `--timeout`.

Default outputs are written to `reproduced/` **next to** the editable master files:

- Seven ASC sheets: three blocks, three standalone test benches, one full DTMF circuit.
- Matching hierarchy/primitive ASY symbols, supplied device models and `models.inc`.
- Four `*_extracted.cir` batch netlists, generated from actual ASC/ASY connections.
- `verification/*_preview.png` for all seven sheets, `connectivity_check.json`, `reproduction.json`.
- With `--simulate`: native RAW/LOG files, readable verification logs and run status/timing/hash records.

Use another output directory or recheck an existing build:

```bash
python scripts/reproduce.py --output-dir /path/to/rebuilt_circuit
python scripts/reproduce.py --check-only --output-dir reproduced
```

`build_project.py` is the schematic source generator and contains the fixed design values/drawing coordinates. `check_project.py` reads ASC/ASY files, checks ports/connections against `reference/circuit.cir`, extracts simulation netlists, then renders previews. The preserved reference is copied from the corrected nominal ngspice circuit. The TL074 source and diode library are read locally, with no downloads.

Manual edits to master/generated ASC files are not imported back into the generator. For a reproducible design change, update the generator and the reference netlist consistently, then rebuild. A check of a deliberately changed circuit will reject a mismatch with the fixed reference. A recheck also regenerates extracted CIR files. Rebuilding the default output replaces earlier generated files there; stale native RAW/LOG files are removed before each new native simulation. It does not overwrite the master ASC/ASY files at this folder's top level.

The full-project launcher `Oscillator/reproduce.py --stage ltspice` invokes this same workflow. The low/high `refinement/circuits/selected_*/LTspice/` folders are standalone snapshots, not linked copies. Use this master generator to create a consistent complete set.
