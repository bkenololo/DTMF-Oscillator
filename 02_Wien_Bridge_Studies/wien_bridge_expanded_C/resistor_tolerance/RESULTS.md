# Resistor tolerance simulation results

Only R1/R2 physical parts vary; C1=C2=10 nF. Final selected nominal resistor combinations are retained.

| Target (Hz) | Resistor tolerance | Sampled settled frequency range (Hz) | Settled samples |
|---:|---:|---:|---:|
| 770 | ±1% | 762.01–777.38 | 81/81 |
| 770 | ±5% | 733.01–810.08 | 81/81 |
| 770 | ±10% | 699.72–855.03 | 81/81 |
| 1209 | ±1% | 1196.94–1221.08 | 81/81 |
| 1209 | ±5% | 1151.41–1272.40 | 81/81 |
| 1209 | ±10% | 1099.15–1342.96 | 81/81 |

486 scenario rows, 482 unique ngspice transient simulations, zero simulator failures. All sampled cases settled. Nominal frequencies reproduce the previously verified selected values. Each physical resistor in every netlist was checked against the requested tolerance value.

These ranges are measured from a finite deterministic grid. The individual component tolerances are independently applied; the ranges are not statistical confidence intervals. See README.md for assumptions and usage.
