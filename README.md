# Votrax SC-01A Python Emulator

A Python software emulation of the Votrax SC-01A speech synthesizer chip, ported from MAME's implementation. This project includes both a command-line interface and a modern GUI with English-to-Phoneme conversion.

## Quick Start (Windows)

1. **Get the ROM**: You must have the `sc01a.bin` file (CRC32: `fc416227`) in this folder. This is the internal ROM dump of the Votrax chip. (You must find this yourself)
2. **Run**: Double-click `run_gui.bat`.
   - This script will automatically create a virtual environment, install necessary dependencies, and launch the GUI.

## Manual Installation

If you are on Linux/Mac or prefer to run manually:

1. **Install Python 3.8+**
2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *Or install individually: `pip install numpy numba g2p_en nltk`*
   *(Note: `winsound` is used for playback in the GUI, which is Windows-specific. On other platforms, you can use the CLI or modify the script to use `pyaudio` or `sounddevice`.)*
3. **Place ROM**: Ensure `sc01a.bin` is in the project directory.

## Features

- **GUI app (`votrax_gui.py`)**:
  - **English-to-Phoneme**: Type regular English text, and it will be converted to Votrax phonemes automatically using `g2p_en`.
  - **Raw Mode**: Toggle "Raw Phonemes Mode" to manually enter Votrax phoneme codes (e.g., `PA0 H EH3 L L O PA1`).
  - **Playback**: Real-time synthesis and playback.
  - **Save WAV**: Export the synthesized speech to a `.wav` file.
  - **Phoneme Reference**: Double-click phonemes from the side panel to insert them.

## CLI Usage (`votrax.py`)

You can also use the backend script directly from the command line:

```bash
python votrax.py "PHONEME LIST" sc01a.bin output.wav
```

### Example

To say "HELLO":

```bash
python votrax.py "H EH3 L L O" sc01a.bin hello.wav
```

## Phonemes

The following phonemes are supported (standard Votrax SC-01A set):

`EH3`, `EH2`, `EH1`, `PA0`, `DT`, `A1`, `A2`, `ZH`, `AH2`, `I3`, `I2`, `I1`, `M`, `N`, `B`, `V`, `CH`, `SH`, `Z`, `AW1`, `NG`, `AH1`, `OO1`, `OO`, `L`, `K`, `J`, `H`, `G`, `F`, `D`, `S`, `A`, `AY`, `Y1`, `UH3`, `AH`, `P`, `O`, `I`, `U`, `Y`, `T`, `R`, `E`, `W`, `AE`, `AE1`, `AW2`, `UH2`, `UH1`, `UH`, `O2`, `O1`, `IU`, `U1`, `THV`, `TH`, `ER`, `EH`, `E1`, `AW`, `PA1`, `STOP`

## Limitations

- **Performance**: The emulation simulates analog filters sample-by-sample. While `numba` is included to help speed this up (if implemented in the backend), it can still be CPU intensive.
- **ROM Required**: The emulation relies on the exact `sc01a.bin` ROM data to function. Without it, the output will be silence or garbage.

