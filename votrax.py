
import math
import struct
import wave
import sys
import os

# Try to import numpy
try:
    import numpy as np
except ImportError:
    print("Numpy is required. Please install it with: pip install numpy")
    sys.exit(1)

# Check for Numba
try:
    from numba import jitclass, int32, uint32, float64, boolean, double
    from numba import jit
    HAS_NUMBA = True
except ImportError:
    print("Numba not found, simulation will be slow. Install with: pip install numba")
    HAS_NUMBA = False
    # Dummy jit decorators
    def jit(nopython=True):
        def decorator(func):
            return func
        return decorator

# Constants
CLOCK_FREQ = 720000 # Default clock
S_GLOTTAL_WAVE = [
    0.0,
    -4.0/7.0,
    7.0/7.0,
    6.0/7.0,
    5.0/7.0,
    4.0/7.0,
    3.0/7.0,
    2.0/7.0,
    1.0/7.0
]

S_PHONE_TABLE = [
    "EH3",  "EH2",  "EH1",  "PA0",  "DT",   "A1",   "A2",   "ZH",
    "AH2",  "I3",   "I2",   "I1",   "M",    "N",    "B",    "V",
    "CH",   "SH",   "Z",    "AW1",  "NG",   "AH1",  "OO1",  "OO",
    "L",    "K",    "J",    "H",    "G",    "F",    "D",    "S",
    "A",    "AY",   "Y1",   "UH3",  "AH",   "P",    "O",    "I",
    "U",    "Y",    "T",    "R",    "E",    "W",    "AE",   "AE1",
    "AW2",  "UH2",  "UH1",  "UH",   "O2",   "O1",   "IU",   "U1",
    "THV",  "TH",   "ER",   "EH",   "E1",   "AW",   "PA1",  "STOP"
]


def bitswap(val, *bits):
    """
    Extracts bits from val at positions specified by *bits (MSB to LSB of result)
    and constructs a new integer.
    E.g. bitswap(0xF, 0, 1) -> takes bit 0 and bit 1 of 0xF -> result bit 1 is val[0], result bit 0 is val[1]
    Wait, MAME bitswap<N>(val, bN-1, ..., b0)
    So the first argument in the list is the position in 'val' that goes to the MSB of the result.
    """
    res = 0
    msg_bits_len = len(bits)
    for i, bit_pos in enumerate(bits):
        bit_val = (val >> bit_pos) & 1
        # Place at position (msg_bits_len - 1 - i)
        res |= (bit_val << (msg_bits_len - 1 - i))
    return res

def bits_to_caps(val, caps):
    total = 0.0
    for i, cap in enumerate(caps):
        if (val >> i) & 1:
            total += cap
    return total

class VotraxSC01A:
    def __init__(self, rom_path, clock=720000):
        self.mainclock = clock
        self.sclock = self.mainclock / 18.0
        self.cclock = self.mainclock / 36.0
        
        self.load_rom(rom_path)
        self.reset()

    def load_rom(self, path):
        if not os.path.exists(path):
            print(f"Warning: ROM file {path} not found. Synthesizer will likely produce garbage.") 
            # We create a dummy ROM so it doesn't crash, but it won't talk.
            self.rom_data = bytes([0]*512)
            return
        
        with open(path, "rb") as f:
            self.rom_data = f.read(512)
        
        if len(self.rom_data) != 512:
            raise ValueError("ROM file must be exactly 512 bytes.")

    def reset(self):
        self.phone = 0x3F
        self.inflection = 0
        self.ar_state = 1 # Asserted (high?) code says ASSERT_LINE. Typically 1.
        self.sample_count = 0
        
        self.phonetick = 0
        self.ticks = 0
        
        # Internal registers
        self.cur_fa = 0
        self.cur_fc = 0
        self.cur_va = 0
        self.cur_f1 = 0
        self.cur_f2 = 0
        self.cur_f2q = 0
        self.cur_f3 = 0
        
        # Filter targets
        self.rom_duration = 0
        self.rom_cld = 0
        self.rom_vd = 0
        self.rom_closure = 0
        self.rom_pause = False
        
        self.rom_fa = 0
        self.rom_va = 0
        self.rom_f2 = 0
        self.rom_fc = 0
        self.rom_f2q = 0
        self.rom_f3 = 0
        self.rom_f1 = 0

        self.filt_fa = 0
        self.filt_fc = 0
        self.filt_va = 0
        self.filt_f1 = 0
        self.filt_f2 = 0
        self.filt_f2q = 0
        self.filt_f3 = 0

        self.pitch = 0
        self.closure = 0
        self.cur_closure = True
        self.update_counter = 0
        self.noise = 0
        self.cur_noise = False

        # Filter histories (arrays)
        self.voice_1 = np.zeros(4, dtype=np.float64)
        self.voice_2 = np.zeros(4, dtype=np.float64)
        self.voice_3 = np.zeros(4, dtype=np.float64)
        self.noise_1 = np.zeros(4, dtype=np.float64)
        self.noise_2 = np.zeros(4, dtype=np.float64)
        self.noise_3 = np.zeros(4, dtype=np.float64)
        self.noise_4 = np.zeros(4, dtype=np.float64)
        
        self.vn_1 = np.zeros(4, dtype=np.float64)
        self.vn_2 = np.zeros(4, dtype=np.float64)
        self.vn_3 = np.zeros(4, dtype=np.float64)
        self.vn_4 = np.zeros(4, dtype=np.float64)
        self.vn_5 = np.zeros(4, dtype=np.float64)
        self.vn_6 = np.zeros(4, dtype=np.float64)

        # Filter coefficients (a array, b array)
        # We need size 4 for most filters
        self.f1_a = np.zeros(4, dtype=np.float64)
        self.f1_b = np.zeros(4, dtype=np.float64)
        self.f2v_a = np.zeros(4, dtype=np.float64)
        self.f2v_b = np.zeros(4, dtype=np.float64)
        self.f2n_a = np.zeros(4, dtype=np.float64)
        self.f2n_b = np.zeros(4, dtype=np.float64)
        self.f3_a = np.zeros(4, dtype=np.float64)
        self.f3_b = np.zeros(4, dtype=np.float64)
        self.f4_a = np.zeros(4, dtype=np.float64)
        self.f4_b = np.zeros(4, dtype=np.float64)
        self.fx_a = np.zeros(4, dtype=np.float64)
        self.fx_b = np.zeros(4, dtype=np.float64)
        self.fn_a = np.zeros(4, dtype=np.float64)
        self.fn_b = np.zeros(4, dtype=np.float64)

        self.phone_commit()
        self.filters_commit(True)

    def write_phone(self, phone):
        self.phone = phone & 0x3F
        # In a real chip, this latches and starts processing. 
        # We simulate this by resetting immediate counters if needed.
        # But 'phone_commit' happens on a timer in the real chip. 
        # We will assume immediate commit for this simple emulator usage or check timing.
        # The code schedules T_COMMIT_PHONE. 
        self.phone_commit() # Simplified synchronous commit

    def phone_commit(self):
        self.phonetick = 0
        self.ticks = 0
        
        # Read from ROM (64-bit entries)
        # The ROM is NOT indexed by phone code. We must search for the entry
        # where the top 6 bits match the current phone code.
        found = False
        val = 0
        for i in range(64):
            idx = i * 8
            val_bytes = self.rom_data[idx:idx+8]
            candidate_val = struct.unpack('<Q', val_bytes)[0]
            
            # Check bits 56-61 (0x3F shifted)
            # stored phone is (val >> 56) & 0x3F
            if self.phone == ((candidate_val >> 56) & 0x3F):
                val = candidate_val
                found = True
                break
        
        if not found:
            # Should not happen if ROM is good and phone is 0-63
            # But just in case, default to 0 (Silence/PA0 usually safe)
            val = 0


        # Decoding logic from votrax.cpp
        # m_rom_f1  = bitswap(val,  0,  7, 14, 21);
        self.rom_f1 = bitswap(val, 0, 7, 14, 21)
        self.rom_va = bitswap(val, 1, 8, 15, 22)
        self.rom_f2 = bitswap(val, 2, 9, 16, 23)
        self.rom_fc = bitswap(val, 3, 10, 17, 24)
        self.rom_f2q = bitswap(val, 4, 11, 18, 25)
        self.rom_f3 = bitswap(val, 5, 12, 19, 26)
        self.rom_fa = bitswap(val, 6, 13, 20, 27)

        self.rom_cld = bitswap(val, 34, 32, 30, 28)
        self.rom_vd = bitswap(val, 35, 33, 31, 29)
        self.rom_closure = bitswap(val, 36)
        
        # Duration: bitswap(~val, 37, 38, 39, 40, 41, 42, 43)
        # Note ~val in Python might be tricky due to flexible int size. 
        # Use XOR with a mask of all 1s (for 64 bit) or just invert bits manually.
        # 37..43 are 7 bits.
        inv_val = val ^ 0xFFFFFFFFFFFFFFFF
        self.rom_duration = bitswap(inv_val, 37, 38, 39, 40, 41, 42, 43)
        
        self.rom_pause = (self.phone == 0x03) or (self.phone == 0x3E)
        
        if self.rom_cld == 0:
            self.cur_closure = (self.rom_closure != 0)

    def filters_commit(self, force):
        # Implementation of filter updates based on current registers
        # This mirrors votrax.cpp filters_commit
        
        self.filt_fa = self.cur_fa >> 4
        self.filt_fc = self.cur_fc >> 4
        self.filt_va = self.cur_va >> 4

        update_f1 = force
        if self.filt_f1 != (self.cur_f1 >> 4):
            self.filt_f1 = self.cur_f1 >> 4
            update_f1 = True
        
        if update_f1:
            caps = bits_to_caps(self.filt_f1, [2546, 4973, 9861, 19724])
            # build_standard_filter(m_f1_a, m_f1_b, 11247, 11797, 949, 52067, 2280 + caps, 166272);
            self.build_standard_filter(self.f1_a, self.f1_b, 11247, 11797, 949, 52067, 2280 + caps, 166272)

        update_f2 = force
        if self.filt_f2 != (self.cur_f2 >> 3) or self.filt_f2q != (self.cur_f2q >> 4):
            self.filt_f2 = self.cur_f2 >> 3
            self.filt_f2q = self.cur_f2q >> 4
            update_f2 = True
            
        if update_f2:
            caps_q = bits_to_caps(self.filt_f2q, [1390, 2965, 5875, 11297])
            caps_v = bits_to_caps(self.filt_f2, [833, 1663, 3164, 6327, 12654])
            
            self.build_standard_filter(self.f2v_a, self.f2v_b, 24840, 29154, 829+caps_q, 38180, 2352+caps_v, 34270)
            self.build_injection_filter(self.f2n_a, self.f2n_b, 29154, 829+caps_q, 38180, 2352+caps_v, 34270)

        update_f3 = force
        if self.filt_f3 != (self.cur_f3 >> 4):
            self.filt_f3 = self.cur_f3 >> 4
            update_f3 = True
            
        if update_f3:
            caps = bits_to_caps(self.filt_f3, [2226, 4485, 9056, 18111])
            self.build_standard_filter(self.f3_a, self.f3_b, 0, 17594, 868, 18828, 8480+caps, 50019)

        if force:
            self.build_standard_filter(self.f4_a, self.f4_b, 0, 28810, 1165, 21457, 8558, 7289)
            self.build_lowpass_filter(self.fx_a, self.fx_b, 1122, 23131)
            self.build_noise_shaper_filter(self.fn_a, self.fn_b, 15500, 14854, 8450, 9523, 14083)

    def build_standard_filter(self, a, b, c1t, c1b, c2t, c2b, c3, c4):
        # Implementation of the bilinear transform logic
        # Need to be careful with floating point math
        k0 = c1t / (self.cclock * c1b)
        k1 = c4 * c2t / (self.cclock * c1b * c3)
        k2 = c4 * c2b / (self.cclock * self.cclock * c1b * c3)

        val = k0*k1 - k2
        fpeak = math.sqrt(abs(val)) / (2 * math.pi * k2)
        
        zc = 2 * math.pi * fpeak / math.tan(math.pi * fpeak / self.sclock)
        
        m0 = zc * k0
        m1 = zc * k1
        m2 = zc * zc * k2
        
        a[0] = 1 + m0
        a[1] = 3 + m0
        a[2] = 3 - m0
        a[3] = 1 - m0
        b[0] = 1 + m1 + m2
        b[1] = 3 + m1 - m2
        b[2] = 3 - m1 - m2
        b[3] = 1 - m1 + m2

    def build_lowpass_filter(self, a, b, c1t, c1b):
        k = c1b / (self.cclock * c1t) * (150.0/4000.0)
        fpeak = 1.0 / (2*math.pi*k)
        zc = 2*math.pi*fpeak / math.tan(math.pi*fpeak / self.sclock)
        m = zc * k
        a[0] = 1.0
        b[0] = 1 + m
        b[1] = 1 - m

    def build_noise_shaper_filter(self, a, b, c1, c2t, c2b, c3, c4):
        k0 = c2t*c3*c2b/c4
        k1 = c2t*(self.cclock * c2b)
        k2 = c1*c2t*c3/(self.cclock * c4)
        
        fpeak = math.sqrt(1.0/k2) / (2*math.pi)
        zc = 2*math.pi*fpeak / math.tan(math.pi*fpeak / self.sclock)
        
        m0 = zc * k0
        m1 = zc * k1
        m2 = zc * zc * k2
        
        a[0] = m0
        a[1] = 0
        a[2] = -m0
        b[0] = 1 + m1 + m2
        b[1] = 2 - 2*m2
        b[2] = 1 - m1 + m2

    def build_injection_filter(self, a, b, c1b, c2t, c2b, c3, c4):
        k0 = self.cclock * c2t
        k1 = self.cclock * (c1b * c3 / c2t - c2t)
        k2 = c2b
        
        zc = 2 * self.sclock
        m = zc * k2
        
        a[0] = k0 + m
        a[1] = k0 - m
        b[0] = k1 - m
        b[1] = k1 + m
        
        # Neutralize unstable filter as per votrax.cpp
        a[0] = 0
        a[1] = 0
        b[0] = 1
        b[1] = 0

    def generate_samples(self, count):
        # Generate 'count' samples
        # This loop needs to be optimized!
        samples = np.zeros(count, dtype=np.float32)
        
        for i in range(count):
            self.sample_count += 1
            if self.sample_count & 1:
                self.chip_update()
            
            samples[i] = self.analog_calc()
            
        return samples

    def interpolate(self, reg, target):
        return reg - (reg >> 3) + (target << 1)

    def chip_update(self):
        # Logic from votrax.cpp chip_update
        if self.ticks != 0x10:
            self.phonetick += 1
            if self.phonetick == ((self.rom_duration << 2) | 1):
                self.phonetick = 0
                self.ticks += 1
                if self.ticks == self.rom_cld:
                    self.cur_closure = (self.rom_closure != 0)

        self.update_counter += 1
        if self.update_counter == 0x30:
            self.update_counter = 0
            
        tick_625 = ((self.update_counter & 0xF) == 0)
        tick_208 = (self.update_counter == 0x28)
        
        if tick_208 and (not self.rom_pause or (self.filt_fa != 0 or self.filt_va != 0)):
            self.cur_fc = self.interpolate(self.cur_fc, self.rom_fc)
            self.cur_f1 = self.interpolate(self.cur_f1, self.rom_f1)
            self.cur_f2 = self.interpolate(self.cur_f2, self.rom_f2)
            self.cur_f2q = self.interpolate(self.cur_f2q, self.rom_f2q)
            self.cur_f3 = self.interpolate(self.cur_f3, self.rom_f3)
            
        if tick_625:
            if self.ticks >= self.rom_vd:
                self.cur_fa = self.interpolate(self.cur_fa, self.rom_fa)
            if self.ticks >= self.rom_cld:
                self.cur_va = self.interpolate(self.cur_va, self.rom_va)

        if not self.cur_closure and (self.filt_fa or self.filt_va):
            self.closure = 0
        elif self.closure != (7 << 2):
            self.closure += 1
            
        self.pitch = (self.pitch + 1) & 0xFF
        target_pitch = (0xE0 ^ (self.inflection << 5) ^ (self.filt_f1 << 1)) + 2
        
        if self.pitch == target_pitch:
            self.pitch = 0
            
        if (self.pitch & 0xF9) == 0x08:
            self.filters_commit(False)
            
        # Noise
        inp = (1 or self.filt_fa) and self.cur_noise and (self.noise != 0x7FFF)
        # Note: (1 or ...) is always True in Python. C++: (1||m_filt_fa).
        # Wait, m_filt_fa is int. 1||x is 1. 
        # So inp = 1 && m_cur_noise && ...
        # If m_cur_noise is bool.
        inp_bit = 1 if (self.cur_noise and self.noise != 0x7FFF) else 0
        
        self.noise = ((self.noise << 1) & 0x7FFE) | inp_bit
        # m_cur_noise = !(((m_noise >> 14) ^ (m_noise >> 13)) & 1);
        bit_xor = ((self.noise >> 14) ^ (self.noise >> 13)) & 1
        self.cur_noise = (bit_xor == 0)

    def shift_hist(self, val, hist):
        hist[1:] = hist[:-1]
        hist[0] = val

    def apply_filter(self, x, y, a, b):
        # x is input history (x[0] is current)
        # y is output history (y[0] is previous output 'y[-1]')
        
        # y[0]_new = ( (x[0]*a[0] + x[1]*a[1] + x[2]*a[2] + x[3]*a[3]) 
        #            - (y[0]*b[1] + y[1]*b[2] + y[2]*b[3]) ) / b[0]
        
        num = (x[0]*a[0] + x[1]*a[1] + x[2]*a[2] + x[3]*a[3])
        den = (y[0]*b[1] + y[1]*b[2] + y[2]*b[3])
        val = (num - den) / b[0]
        return val

    def analog_calc(self):
        # Voice-only path
        # 1. Pick up the pitch wave
        pitch_idx = self.pitch >> 3
        if pitch_idx < 9:
             v = S_GLOTTAL_WAVE[pitch_idx]
        else:
             v = 0.0

        # 2. Multiply by the initial amplifier.
        v = v * self.filt_va / 15.0
        self.shift_hist(v, self.voice_1)

        # 3. Apply the f1 filter
        v = self.apply_filter(self.voice_1, self.voice_2, self.f1_a, self.f1_b)
        self.shift_hist(v, self.voice_2)

        # 4. Apply the f2 filter, voice half
        v = self.apply_filter(self.voice_2, self.voice_3, self.f2v_a, self.f2v_b)
        self.shift_hist(v, self.voice_3)

        # Noise-only path
        # 5. Pick up the noise pitch.
        # (m_pitch & 0x40 ? m_cur_noise : false) ? 1 : -1
        if (self.pitch & 0x40) and self.cur_noise:
            noise_val = 1.0
        else:
            noise_val = -1.0
            
        n = 10000.0 * noise_val
        n = n * self.filt_fa / 15.0
        self.shift_hist(n, self.noise_1)

        # 6. Apply the noise shaper
        n = self.apply_filter(self.noise_1, self.noise_2, self.fn_a, self.fn_b)
        self.shift_hist(n, self.noise_2)

        # 7. Scale with the f2 noise input
        n2 = n * self.filt_fc / 15.0
        self.shift_hist(n2, self.noise_3)

        # 8. Apply the f2 filter, noise half
        n2 = self.apply_filter(self.noise_3, self.noise_4, self.f2n_a, self.f2n_b)
        self.shift_hist(n2, self.noise_4)

        # Mixed path
        # 9. Add the f2 voice and f2 noise outputs
        vn = v + n2
        self.shift_hist(vn, self.vn_1)

        # 10. Apply the f3 filter
        vn = self.apply_filter(self.vn_1, self.vn_2, self.f3_a, self.f3_b)
        self.shift_hist(vn, self.vn_2)

        # 11. Second noise insertion
        # vn += n * (5 + (15^m_filt_fc))/20.0;
        vn += n * (5 + (15 ^ self.filt_fc)) / 20.0
        self.shift_hist(vn, self.vn_3)

        # 12. Apply the f4 filter
        vn = self.apply_filter(self.vn_3, self.vn_4, self.f4_a, self.f4_b)
        self.shift_hist(vn, self.vn_4)

        # 13. Apply the glottal closure amplitude
        vn = vn * (7 ^ (self.closure >> 2)) / 7.0
        self.shift_hist(vn, self.vn_5)

        # 13. Apply the final fixed filter
        vn = self.apply_filter(self.vn_5, self.vn_6, self.fx_a, self.fx_b)
        self.shift_hist(vn, self.vn_6)

        return vn * 0.35

    def get_phoneme_duration_samples(self):
        # Calculate duration in samples for the current phoneme
        # Duration = 32 * (rom_duration * 4 + 1)
        # Based on chip_update logic and sample rate
        return 32 * (self.rom_duration * 4 + 1)

def text_to_phonemes(text):
    # Simple mapping from text names to indices
    # e.g. "H EH3 L L O"
    tokens = text.upper().split()
    indices = []
    
    # helper for phoneme map
    phone_map = {name: i for i, name in enumerate(S_PHONE_TABLE)}
    
    for token in tokens:
        if token in phone_map:
            indices.append(phone_map[token])
        else:
            print(f"Warning: Phoneme '{token}' not recognized.")
            # Default to PA0 (3)
            indices.append(3)
    return indices

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Votrax SC-01A Emulator")
    parser.add_argument("phonemes", help="String of space-separated phonemes (e.g., 'H EH1 L O')")
    parser.add_argument("rom", help="Path to sc01a.bin")
    parser.add_argument("output", help="Output WAV file", default="output.wav")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.rom):
        print(f"Error: ROM file '{args.rom}' not found.")
        sys.exit(1)

    print(f"Initializing Votrax SC-01A with ROM: {args.rom}")
    votrax = VotraxSC01A(args.rom)
    
    phoneme_indices = text_to_phonemes(args.phonemes)
    print(f"Phoneme indices: {phoneme_indices}")
    
    all_samples = []
    
    for p_idx in phoneme_indices:
        print(f"Synthesizing phoneme: {S_PHONE_TABLE[p_idx]} ({p_idx})")
        votrax.write_phone(p_idx)
        
        # Calculate duration
        # Note: write_phone commits immediately in our simplified status, 
        # so rom_duration is updated.
        num_samples = votrax.get_phoneme_duration_samples()
        
        # Generate samples
        samples = votrax.generate_samples(num_samples)
        all_samples.append(samples)
        
    # Concatenate
    if all_samples:
        final_wave = np.concatenate(all_samples)
        
        # Normalize?
        # analog_calc returns values that might be small or large. 
        # Votrax output is analog.
        max_val = np.max(np.abs(final_wave))
        if max_val > 0:
            final_wave = final_wave / max_val * 0.8
        
        # Convert to 16-bit PCM
        final_data = (final_wave * 32767).astype(np.int16)
        
        print(f"Writing {len(final_data)} samples to {args.output}")
        with wave.open(args.output, 'w') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(int(votrax.sclock))
            wav_file.writeframes(final_data.tobytes())
        print("Done.")
    else:
        print("No samples generated.")

