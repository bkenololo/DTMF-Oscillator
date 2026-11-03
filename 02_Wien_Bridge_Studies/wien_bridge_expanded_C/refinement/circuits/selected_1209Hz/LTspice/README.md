# HighOscillator LTspice standalone copy

Open Test_HighOscillator.asc to simulate. Open HighOscillator.asc to inspect the components.
HighOscillator.asy is its reusable hierarchical symbol. Keep this folder together.

This is a self-contained snapshot placed alongside the refined oscillator netlist.
The complete three-block DTMF project, full documentation, and master editable sheets are at:

/Users/bkent/Documents/Academic/ITB/Semester Ganjil 26:27/Elektronika II/2026/Proyek/Oscillator/03_Summing_Amplifier/wien_dtmf_summing_corrected/circuits/LTspice_DTMF

To change the complete DTMF circuit, edit the child ASC in that master directory.
Changes made to this standalone copy do not propagate to the master directory.

Connectivity was checked against the corrected netlist; the extracted CIR was simulated
successfully with LTspice 17.2.4. GUI opening/hierarchy traversal was not verified.
The PNG is rendered from ASC/ASY geometry, not a native LTspice screenshot.

## Reproducible source

This folder is a standalone snapshot. Use the [master LTspice generator](../../../../../../03_Summing_Amplifier/wien_dtmf_summing_corrected/circuits/LTspice_DTMF/README.md) to rebuild both oscillator blocks, the summer, all matching symbols and the complete DTMF circuit together. Rebuilt files go into the master folder’s `reproduced/` directory.
