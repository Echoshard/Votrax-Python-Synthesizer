
# Votrax SC-01A Python Emulator

This is a Python software emulation of the Votrax SC-01A speech synthesizer chip, ported from MAME's C++ implementation.

## Requirements

- Python 3
- NumPy (`pip install numpy`)
- **sc01a.bin**: This is the internal ROM dump of the Votrax SC-01A chip (CRC32: fc416227). You must place this file in the same directory or provide the path to it.

## Usage

Run the script from the command line:

```bash
python votrax.py "PHONEME LIST" sc01a.bin output.wav
```

### Example

To say "HELLO":

```bash
python votrax.py "H EH3 L L O" sc01a.bin hello.wav
```

The script will generate a WAV file `hello.wav` with the synthesized speech.

## Phonemes

The following phonemes are supported (standard Votrax SC-01A set):

EH3, EH2, EH1, PA0, DT, A1, A2, ZH, AH2, I3, I2, I1, M, N, B, V, CH, SH, Z, AW1, NG, AH1, OO1, OO, L, K, J, H, G, F, D, S, A, AY, Y1, UH3, AH, P, O, I, U, Y, T, R, E, W, AE, AE1, AW2, UH2, UH1, UH, O2, O1, IU, U1, THV, TH, ER, EH, E1, AW, PA1, STOP

## Limitations

- The emulation is computationally intensive because it simulates the analog filters sample-by-sample. Using PyPy or Numba-optimized Python is recommended for real-time performance, though this script uses standard Python/NumPy (offline rendering is fine).
- You MUST have the correct `sc01a.bin` file. Without it, the output will be silence or garbage.
