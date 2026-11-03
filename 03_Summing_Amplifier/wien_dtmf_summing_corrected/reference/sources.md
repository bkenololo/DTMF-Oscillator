# References used for this stage

- `Perhitungan.docx`, supplied by the user: summing Rin=22 kΩ at each input, Rf=10 kΩ; resistor BOM specifies 1%; ±12 V supplies; gain control 10 kΩ / 15 kΩ / 7.5 kΩ with antiparallel 1N4148; supply bypass capacitors. The older oscillator frequency-setting values in the document are superseded by the user's request to retain the final refined values in `selected_nominal_values.json`.
- [TI TL07xx datasheet](https://www.ti.com/lit/ds/symlink/tl074.pdf): device and four-channel context. Simulation uses the supplied historical model, not a substituted current TL074H model.
- [TI Universal Multifrequency receiver documentation](https://www.ti.com/lit/ug/spru638/spru638.pdf): the DTMF keypad table maps 770 Hz + 1209 Hz to digit 4. This document's receiver behavior is not reproduced or claimed by the basic spectral checker included here.
- `copied_auxiliary_hashes.json` and `models/provenance.json`: hashes and provenance of the copied simulator and device models.
