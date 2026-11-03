# Standalone tolerance test — pinned resistor pairs

Run from the V2 folder:

```bash
python resistor_tolerance_table_values/run_resistor_tolerance.py --workers 4
```

Or from `Oscillator`: `python reproduce.py --stage resistor-tolerance`.

Inputs are local `selected_parameters.json` plus the existing V2 `config.json`, model libraries and simulator core. Nominal values are low R1=20620 Ω/R2=20560 Ω and high R1=13082 Ω/R2=13110 Ω, with two 10-nF capacitors per oscillator. The standalone maximum timestep is 5 µs, matching the user-selected table; this differs from the corrected combined-circuit nominal test's 1.25 µs.

Each leg uses two series resistors. Each physical resistor independently takes −tolerance, nominal or +tolerance at ±1%, ±5%, ±10%: 81 combinations per tolerance per oscillator, 486 scenario rows before physical deduplication. Outputs are `resistor_tolerance_770Hz.csv`, `resistor_tolerance_1209Hz.csv`, `resistor_tolerance_summary.csv`, `figures/`, case logs and `validation.json`. They are generated on first run; the historical `../resistor_tolerance/` results remain separate.

The script retains the frozen nominal-frequency assertion from the original table-based study. Cross-platform/simulator numerical differences may fail that assertion and require inspection. They must not be relabeled as successful reproduction without checking settings and logs.
