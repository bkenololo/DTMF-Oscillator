# Expanded Wien bridge sweep overview

The requested broad sweep varies standard nominal capacitors, then independently tests the ±1%, ±5%, and ±10% endpoints of both capacitors at every nominal value. The original resistor grids, circuit and simulation settings are retained.

A separately labelled fine-resistor search improves nominal frequency matching using neighboring E24 values in the existing series combinations. It is not conflated with the unchanged-resistor broad capacitor search.

| Target Hz | Search | C1=C2 nF | R1 Ω | R2 Ω | Simulated Hz | Error % | THD 2–10 % |
|---:|---|---:|---:|---:|---:|---:|---:|
| 770 | previous_10nF | 10 | 20680 | 20680 | 766.2090 | 0.4923 | 3.845 |
| 770 | broad_C | 10 | 20680 | 20680 | 766.2090 | 0.4923 | 3.845 |
| 770 | fine_R | 10 | 20620 | 20560 | 769.5837 | 0.0541 | 3.825 |
| 1209 | previous_10nF | 10 | 13000 | 13150 | 1210.9206 | 0.1589 | 3.913 |
| 1209 | broad_C | 11 | 13000 | 11000 | 1207.1703 | 0.1513 | 1.496 |
| 1209 | fine_R | 10 | 13082 | 13110 | 1209.0978 | 0.0081 | 3.854 |

**Result:** changing only nominal C within the retained R grid did not improve the 770 Hz match. The finer resistor combinations improve it while retaining nominal 10 nF. For 1209 Hz, the broad sweep provides an 11 nF option with lower distortion; the fine-resistor sweep provides a closer nominal frequency at 10 nF.

The comparison table above uses the common 5 µs grid setting. Finalists below are additionally compared at a finer common timestep when the verification results are present.

## Closest nominal frequency choices

- **770 Hz:** C1=C2=10 nF; R1=20000 + 620 Ω; R2=20000 + 560 Ω. Simulated 769.6176 Hz at 1.25 µs maximum timestep; 769.6193 Hz at half that timestep.
- **1209 Hz:** C1=C2=10 nF; R1=13000 + 100 Ω; R2=13000 + 100 Ω. Simulated 1208.8873 Hz at 1.25 µs maximum timestep; 1208.8939 Hz at half that timestep.

These are the closest nominal-frequency cases in the finite search, not universal optima. The smallest frequency error does not imply lowest distortion. Numerical timestep differences limit meaningful precision, and capacitor manufacturing tolerance still changes the hardware frequency. No lab pass/fail limits have been assumed.

## Data and source files

- Broad capacitor sweep: [report](results/RESULTS.md), [HTML](results/index.html).
- Separate fine resistor sweep: [report](refinement/results/RESULTS.md), [HTML](refinement/results/index.html).
- Each stage includes all rows, nominal rankings, best pair at each C, tolerance grids, case netlists/logs, traces and numerical checks.
- Final nominal components: `selected_nominal_values.json`.
- Final circuit files: `circuits/recommended_770Hz/circuit.cir` and `circuits/recommended_1209Hz/circuit.cir`.
- Running instructions and assumptions: `README.md`.
