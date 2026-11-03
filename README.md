# Oscillator project — start here

Open [00_START_HERE.html](00_START_HERE.html) for clickable navigation.

```text
Oscillator/
├── 00_START_HERE.html
├── README.md
├── reproduce.py                       Common Python launcher
├── requirements.txt                   Python dependencies
├── 01_Project_Documents/
│   ├── description-proyekII-elektronikaII.rtf
│   └── Perhitungan.docx
├── 02_Wien_Bridge_Studies/
│   ├── wien_bridge_lookup/             V1: initial 10 nF study
│   └── wien_bridge_expanded_C/         V2: broader C sweep + R refinement
├── 03_Summing_Amplifier/
│   └── wien_dtmf_summing_corrected/    Current corrected combined circuit
├── 04_Original_Device_Models/
│   └── TL074.301
├── 05_Analisis_Hasil_Uji/             Original evidence + measured-data analysis
└── ORGANIZATION_LOG.json
```

## Current results

Use [the corrected summing overview](03_Summing_Amplifier/wien_dtmf_summing_corrected/START_HERE.html) or [its summary](03_Summing_Amplifier/wien_dtmf_summing_corrected/SUMMARY.md).

- Low oscillator: R1=20,620 Ω, R2=20,560 Ω.
- High oscillator: R1=13,082 Ω, R2=13,110 Ω.
- C1=C2=10 nF in each oscillator.
- Summer: 22 kΩ per input, 10 kΩ feedback.
- [Decoder WAV: 4](03_Summing_Amplifier/wien_dtmf_summing_corrected/audio/dtmf_4_steady_48k.wav).
- [Repeated decoder WAV: 444](03_Summing_Amplifier/wien_dtmf_summing_corrected/audio/dtmf_4_repeated_48k.wav).
- [SPICE netlist](03_Summing_Amplifier/wien_dtmf_summing_corrected/circuits/nominal/circuit.cir).
- [BOM](03_Summing_Amplifier/wien_dtmf_summing_corrected/BOM.csv).

## Historical studies

[V1](02_Wien_Bridge_Studies/wien_bridge_lookup/README.md) contains the initial fixed-nominal-10-nF lookup.

[V2](02_Wien_Bridge_Studies/wien_bridge_expanded_C/START_HERE.html) contains the expanded standard-capacitor sweep, [resistor refinement](02_Wien_Bridge_Studies/wien_bridge_expanded_C/refinement/results/RESULTS.md), finer-timestep verification and standalone tolerance results. Different stages selected different resistor pairs. Its 13.1 kΩ / 13.1 kΩ selection is historical; it does not supersede the user's current pinned pair above. Retain the simulation timestep when comparing numerical frequencies between stages.

## Reproduce the simulations and schematics

Use Python 3.10 or newer. Open a terminal in this `Oscillator` folder. All launcher paths are resolved relative to the script, so the project can be moved without editing personal absolute paths. Keep the internal subfolder layout intact.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python reproduce.py --list
```

On Windows, activate with `.venv\Scripts\activate` instead. The `python` commands below then work the same way. The copied `tools/ngspice` executable is a local macOS build; on another platform, install a compatible ngspice build and supply `--ngspice /path/to/executable` (or set `NGSPICE`). Native LTspice is optional and only needed for `ltspice-sim`.

**Quick start: nominal circuit → WAV → local decoder → editable LTspice schematics:**

```bash
python reproduce.py --stage summing-nominal --stage audio --stage decoder --stage ltspice
```

This exports the simulated signal, checks for digit `4`, and rebuilds the low/high/summer blocks, their symbols, standalone test benches and combined DTMF schematic. The local decoder is a spectral sanity check; its settings/results do not reproduce the website's sensitivity threshold test.

**Current pinned design, including tolerance studies, numerical/load checks, figures and reports:**

```bash
python reproduce.py --current --workers 4
```

**Historical sweeps plus the current design:**

```bash
python reproduce.py --all --workers 4 --dry-run
python reproduce.py --all --workers 4
```

The broad V2 sweep has 11,150 physical cases and the refinement has 1,250; these are substantial jobs. `--dry-run` prints commands and writes nothing. Running the script without a stage only lists choices. Existing case caches are reused when their source/configuration/model/simulator fingerprints match; source changes can trigger fresh simulations. `--all` excludes lab reanalysis and native LTspice runs. It does not silently replace the pinned final resistor pairs with a historical selection.

| Stage | Outputs / prerequisites |
|---|---|
| `v1` | Historical fixed-10-nF results in `02_Wien_Bridge_Studies/wien_bridge_lookup/results/`. |
| `v2`, `refinement` | Expanded sweep and fine resistor sweep in V2 `results/` and `refinement/results/`. |
| `verification`, `combine` | Finer-timestep verification and V2 combined overview; run after both V2 sweeps. |
| `resistor-tolerance` | New `V2/resistor_tolerance_table_values/`: independent physical-part ±1%, ±5%, ±10% scenarios using the pinned pairs at the original table's 5 µs maximum timestep. |
| `summing-nominal` | Corrected nominal combined circuit in the summer `results/` and `circuits/nominal/`. |
| `summing` | Full summer tolerance grids plus `results/numerical_and_load_checks.csv`. |
| `standalone` | Standalone low/high reference simulations; comparison with combined-circuit outputs. |
| `audio`, `decoder` | Export summer `audio/` WAVs, then decode the steady 48-kHz WAV; `audio` requires nominal simulation data. |
| `report` | Summer figures/tables/overview; requires full `summing`, `standalone` and `audio` results. |
| `tests` | Existing physics, signal measurement, netlist, antialiasing and decoder tests. |
| `ltspice` | Rebuilt ASC/ASY/CIR/PNG files under the master LTspice folder's `reproduced/`; no LTspice installation needed. |
| `ltspice-sim` | Same rebuild plus four native LTspice batch simulations. |
| `lab` | Recompute measured-data analysis from archived lab evidence; separate Node dependency below. |

You can repeat `--stage` to run selected stages **in the order you supply**. The launcher does not automatically run missing prerequisites. `--current` and `--all` supply the appropriate order. `--workers` controls the sweep stages that accept worker counts; standalone/finalist helpers retain their existing execution behavior.

Every executed launcher run saves console logs, commands, elapsed times, return codes and input-source hashes in `reproduction_logs/<UTC timestamp>/`. A failing stage stops later stages. Scientific outputs remain in their existing study folders and are regenerated when that stage runs. Original lab files under `05_Analisis_Hasil_Uji/01_Data_Asli/` are inputs and are not rewritten.

### LTspice source regeneration

Master: [LTspice_DTMF](03_Summing_Amplifier/wien_dtmf_summing_corrected/circuits/LTspice_DTMF/README.md).

```bash
python reproduce.py --stage ltspice
python reproduce.py --stage ltspice-sim
```

For an executable outside standard locations:

```bash
python reproduce.py --stage ltspice-sim --ltspice /path/to/LTspice
```

The generator writes a separate `reproduced/` folder; editable master files and standalone snapshots remain available. The checker extracts connections from ASC/ASY coordinates and compares all 38 components to the preserved source netlist. Native batch verification runs those extracted CIR files. Automatic GUI hierarchy traversal is not verified. See the master README for file editing versus regeneration and custom output directories.

### Lab reanalysis

Install Node.js separately and install its SVG renderer from the supplied local package file:

```bash
npm install --prefix 05_Analisis_Hasil_Uji/04_Skrip
python reproduce.py --stage lab
```

`NODE_BIN` may select a Node executable; `SHARP_MODULE` may select an existing `sharp` module path. The analysis uses the copied workbook/CSV/WAV/screenshot evidence and the archived public decoder JavaScript already inside `05_Analisis_Hasil_Uji/`. It does not download a new website version. It rewrites derived analyses, figures and the analysis folder's generated README/HTML/manifest. The offline decoder replay is not a new observed browser test.

### Reproduction limits and source locations

- Current summer parameters: `03_Summing_Amplifier/wien_dtmf_summing_corrected/config.json`; pinned resistor table: its `reference/user_selected_table.json`.
- Standalone pinned-resistor tolerance inputs: `02_Wien_Bridge_Studies/wien_bridge_expanded_C/resistor_tolerance_table_values/selected_parameters.json`. Historical `resistor_tolerance/` is retained separately.
- Original model equations and circuit component values are retained. A local code-model alias fixes ngspice loading when an external executable's path contains spaces.
- Simulator version, solver, time step, Python/library versions and numerical platform can change measured frequencies slightly. The historical resistor-tolerance script's exact nominal-frequency assertion is retained: a failure against its frozen table should be investigated, not hidden by rounding.
- The top-level Python requirements specify compatible version ranges, not an environment lock. Each run records available package versions; native simulator logs/version fingerprints provide the remaining runtime context. Compare quantities at matching analysis settings rather than expecting byte-identical plots or results across platforms.
- Existing manifests retain their result-snapshot entries; source entries affected by this update are refreshed. `REPRODUCIBILITY_UPDATE.json` separately records changed/new reproduction files and verification scope. Rerunning report stages can regenerate their own manifests.

## Why internal project names were retained

The complete simulation folders were moved intact. Their netlists, model paths and scripts retain the same relative layout. V1 and V2 stay siblings because V2's comparison configuration uses `../wien_bridge_lookup/results`. No simulation configuration needed changing. Run each project's commands from that project's own directory, not from this top-level folder.

Each project's `models/`, `tools/`, `vendor/`, source and logs remain together for reproducibility. The loose original TL074 model is now in `04_Original_Device_Models/`; model copies used by simulations remain inside each project. Original files and historical results were not deleted or rewritten.

See `ORGANIZATION_LOG.json` for the move map. To reverse the organization, first ensure each old top-level destination is free, then move the six listed items back to their `original` paths. The newly added navigation documents can remain or be removed separately.
