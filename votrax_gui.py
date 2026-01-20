
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import wave
import tempfile
import time
import winsound  # Windows only
import numpy as np

# Import our backend
try:
    import votrax
except ImportError:
    messagebox.showerror("Error", "Could not import 'votrax.py'. Make sure it is in the same directory.")
    sys.exit(1)

# Modern Dark Theme Colors
COLORS = {
    "bg": "#1e1e2e",           # Dark background
    "fg": "#cdd6f4",           # Light text
    "panel": "#313244",        # Lighter panel
    "input_bg": "#45475a",     # Input field background
    "input_fg": "#ffffff",     # Input text
    "accent": "#89b4fa",       # Blue accent
    "accent_hover": "#b4befe", # Lighter blue
    "success": "#a6e3a1",      # Green
    "warning": "#f9e2af",      # Yellow
    "error": "#f38ba8",        # Red
    "border": "#585b70"        # Border color
}

class ModernButton(tk.Canvas):
    """A custom rounded button to look 'modern' in Tkinter."""
    def __init__(self, master, text, command, width=120, height=40, bg=COLORS["accent"], hover_bg=COLORS["accent_hover"]):
        super().__init__(master, width=width, height=height, bg=COLORS["bg"], highlightthickness=0)
        self.command = command
        self.text = text
        self.bg_color = bg
        self.hover_color = hover_bg
        self.current_color = bg
        
        self.draw()
        
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)

    def draw(self):
        self.delete("all")
        # Draw rounded rect (simplified as oval + rect)
        w = int(self["width"])
        h = int(self["height"])
        r = h // 2
        
        # We can't do real anti-aliased rounded rects easily in core Tkinter canvas without jagged edges on dark bg.
        # So we use a rectangle.
        self.create_rectangle(2, 2, w-2, h-2, fill=self.current_color, outline=COLORS["fg"], width=0)
        self.create_text(w//2, h//2, text=self.text, fill=COLORS["bg"], font=("Segoe UI", 10, "bold"))

    def on_enter(self, e):
        self.current_color = self.hover_color
        self.draw()

    def on_leave(self, e):
        self.current_color = self.bg_color
        self.draw()

    def on_click(self, e):
        if self.command:
            self.command()

    def set_text(self, text):
        self.text = text
        self.draw()

class VotraxGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("Votrax SC-01A Emulator")
        self.geometry("900x600")
        self.configure(bg=COLORS["bg"])
        
        # Try to set icon if available, otherwise ignore
        # self.iconbitmap("icon.ico") 

        self.rom_path = os.path.join(os.getcwd(), "sc01a.bin")
        self.synthesizer = None
        self.is_generating = False
        self.stop_requested = False
        
        self.setup_ui()
        self.check_rom()

    def setup_ui(self):
        # Configure Styles
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["fg"], font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"), foreground=COLORS["accent"])
        style.configure("Sub.TLabel", font=("Segoe UI", 12), foreground=COLORS["accent"])
        
        style.configure("TButton", background=COLORS["panel"], foreground=COLORS["fg"], borderwidth=0)
        style.map("TButton", background=[('active', COLORS["accent"])])

        # Main Layout
        main_container = ttk.Frame(self)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Header
        header = ttk.Label(main_container, text="VOTRAX SC-01A", style="Header.TLabel")
        header.pack(anchor="w", pady=(0, 5))
        
        
        # --- Content Area ---
        
        # Content Area (Split: Left Input, Right Reference)
        content_frame = ttk.Frame(main_container)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- Left Side: Input & Controls ---
        left_panel = ttk.Frame(content_frame)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # ROM STATUS
        self.lbl_rom_status = ttk.Label(left_panel, text="Checking ROM...", style="TLabel")
        self.lbl_rom_status.pack(anchor="w", pady=(0, 10))
        
        # Input Label & Mode
        lbl_frame = ttk.Frame(left_panel)
        lbl_frame.pack(fill=tk.X, pady=(0, 5))
        
        lbl_input = ttk.Label(lbl_frame, text="Enter Text (English or Phonemes):", style="Sub.TLabel")
        lbl_input.pack(side=tk.LEFT)
        
        self.var_raw = tk.BooleanVar(value=False)
        self.chk_raw = ttk.Checkbutton(lbl_frame, text="Raw Phonemes Mode", variable=self.var_raw, style="TCheckbutton")
        self.chk_raw.pack(side=tk.RIGHT)
        
        # Text Area
        self.txt_input = tk.Text(left_panel, height=12, bg=COLORS["input_bg"], fg=COLORS["input_fg"], 
                                 insertbackground="white", relief=tk.FLAT, font=("Consolas", 12))
        self.txt_input.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        self.txt_input.insert("1.0", "Hello World I am here to destroy")
        
        # Buttons Frame
        btn_frame = ttk.Frame(left_panel)
        btn_frame.pack(fill=tk.X, pady=10)
        
        self.btn_play = ModernButton(btn_frame, "PLAY AUDIO", self.on_play, bg=COLORS["accent"], hover_bg=COLORS["accent_hover"])
        self.btn_play.pack(side=tk.LEFT, padx=(0, 10))
        
        self.btn_save = ModernButton(btn_frame, "SAVE .WAV", self.on_save, bg=COLORS["panel"], hover_bg="#45475a")
        self.btn_save.pack(side=tk.LEFT)
        
        # Progress Bar
        self.progress = ttk.Progressbar(left_panel, mode='indeterminate')
        # self.progress.pack(fill=tk.X, pady=20) # Hidden by default
        
        self.lbl_status = ttk.Label(left_panel, text="Ready", style="TLabel")
        self.lbl_status.pack(anchor="w", pady=10)
        
        # --- Right Side: Phoneme Reference ---
        right_panel = tk.Frame(content_frame, bg=COLORS["panel"], width=250)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        right_panel.pack_propagate(False) # Force width
        
        lbl_ref = tk.Label(right_panel, text="Phoneme Reference", bg=COLORS["panel"], fg=COLORS["accent"], font=("Segoe UI", 11, "bold"))
        lbl_ref.pack(pady=10)
        
        # Scrollable list
        list_frame = tk.Frame(right_panel, bg=COLORS["panel"])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.phoneme_list = tk.Listbox(list_frame, bg=COLORS["input_bg"], fg=COLORS["input_fg"], 
                                       relief=tk.FLAT, font=("Consolas", 10), yscrollcommand=scrollbar.set)
        self.phoneme_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.phoneme_list.yview)
        
        # Populate List
        for p in votrax.S_PHONE_TABLE:
            self.phoneme_list.insert(tk.END, p)
            
        self.phoneme_list.bind('<Double-1>', self.on_phoneme_double_click)

        # Help Text
        lbl_help = tk.Label(right_panel, text="Double-click to insert", bg=COLORS["panel"], fg=COLORS["fg"], font=("Segoe UI", 8))
        lbl_help.pack(pady=5)

    def check_rom(self):
        if os.path.exists(self.rom_path):
            self.lbl_rom_status.config(text=f"ROM Loaded: {os.path.basename(self.rom_path)}", foreground=COLORS["success"])
            try:
                self.synthesizer = votrax.VotraxSC01A(self.rom_path)
            except Exception as e:
                self.lbl_rom_status.config(text=f"Error Loading ROM: {e}", foreground=COLORS["error"])
        else:
            self.lbl_rom_status.config(text=f"ROM MISSING: {os.path.basename(self.rom_path)}", foreground=COLORS["error"])
            messagebox.showwarning("ROM Missing", f"Could not find 'sc01a.bin' in {os.getcwd()}.\n\nPlease assume you need to find this file (CRC: fc416227) to hear real speech.")

    def on_phoneme_double_click(self, event):
        selection = self.phoneme_list.curselection()
        if selection:
            phoneme = self.phoneme_list.get(selection[0])
            self.txt_input.insert(tk.INSERT, f"{phoneme} ")

            self.txt_input.insert(tk.INSERT, f"{phoneme} ")
            # If user inserts phoneme, maybe auto-enable raw mode?
            self.var_raw.set(True)

    def get_phonemes_from_input(self):
        text = self.txt_input.get("1.0", tk.END).strip()
        if not text:
            return []

        # If Raw Mode, parse directly
        if self.var_raw.get():
             return votrax.text_to_phonemes(text)
             
        # Else, do G2P conversion
        self.lbl_status.config(text="Converting English...", foreground=COLORS["warning"])
        self.update()
        
        # Pre-process numbers
        words = text.split()
        num_map = {
            "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
            "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
            "10": "ten", "11": "eleven", "12": "twelve"
        }
        for i, w in enumerate(words):
            if w in num_map:
                words[i] = num_map[w]
        text_norm = " ".join(words)

        try:
             try:
                 import nltk
                 from g2p_en import G2p
                 try:
                    nltk.data.find('taggers/averaged_perceptron_tagger_eng')
                 except LookupError:
                    nltk.download('averaged_perceptron_tagger_eng', quiet=True)
                 try:
                    nltk.data.find('corpora/cmudict')
                 except LookupError:
                    nltk.download('cmudict', quiet=True)
             except ImportError:
                 messagebox.showerror("Error", "Missing libraries (g2p_en/nltk).")
                 return []

             if not hasattr(self, 'g2p_model'):
                 self.g2p_model = G2p()
                 
             arpabet_phones = self.g2p_model(text_norm)
             
             votrax_phones = []
             for token in arpabet_phones:
                 token_pure = ''.join([c for c in token if c.isalpha()])
                 token_stress = token[-1] if token[-1].isdigit() else None
                 
                 if token == ' ':
                     votrax_phones.append("PA1")
                     continue
                 if not token_pure: continue 

                 # CMU -> Votrax Map
                 v_ph = "PA0" 
                 
                 # Vowels
                 if token_pure == "AA": v_ph = "AH1" if token_stress == '1' else "A2" 
                 elif token_pure == "AE": v_ph = "AE1" if token_stress == '1' else "AE"
                 elif token_pure == "AH": v_ph = "AH1" if token_stress == '1' else "AH"
                 elif token_pure == "AO": v_ph = "AW1" if token_stress == '1' else "AW"
                 elif token_pure == "EH": v_ph = "EH2" if token_stress == '1' else "EH3"
                 elif token_pure == "ER": v_ph = "ER" 
                 elif token_pure == "IH": v_ph = "I1" if token_stress == '1' else "I2"
                 elif token_pure == "UH": v_ph = "OO1"
                 
                 # Diphthongs
                 elif token_pure == "AY": votrax_phones.extend(["AH1", "Y1"]); continue
                 elif token_pure == "OW": votrax_phones.extend(["O1", "U1"]); continue
                 elif token_pure == "OY": votrax_phones.extend(["O1", "I3"]); continue
                 elif token_pure == "AW": votrax_phones.extend(["AH1", "AW2"]); continue
                 elif token_pure == "EY": votrax_phones.extend(["A1", "Y"]); continue
                 elif token_pure == "IY": votrax_phones.extend(["E1", "Y"]); continue
                 elif token_pure == "UW": votrax_phones.extend(["IU", "U1"]); continue
                 
                 # Consonants
                 elif token_pure == "B": v_ph = "B"
                 elif token_pure == "CH": v_ph = "CH"
                 elif token_pure == "D": v_ph = "D"
                 elif token_pure == "DH": v_ph = "THV"
                 elif token_pure == "F": v_ph = "F"
                 elif token_pure == "G": v_ph = "G"
                 elif token_pure == "HH": v_ph = "H"
                 elif token_pure == "JH": v_ph = "J"
                 elif token_pure == "K": v_ph = "K"
                 elif token_pure == "L": v_ph = "L"
                 elif token_pure == "M": v_ph = "M"
                 elif token_pure == "N": v_ph = "N"
                 elif token_pure == "NG": v_ph = "NG"
                 elif token_pure == "P": v_ph = "P"
                 elif token_pure == "R": v_ph = "R"
                 elif token_pure == "S": v_ph = "S"
                 elif token_pure == "SH": v_ph = "SH"
                 elif token_pure == "T": v_ph = "T"
                 elif token_pure == "TH": v_ph = "TH"
                 elif token_pure == "V": v_ph = "V"
                 elif token_pure == "W": v_ph = "W"
                 elif token_pure == "Y": v_ph = "Y"
                 elif token_pure == "Z": v_ph = "Z"
                 elif token_pure == "ZH": v_ph = "ZH"
                 
                 votrax_phones.append(v_ph)
            
             # Convert resulting names to indices
             return votrax.text_to_phonemes(" ".join(votrax_phones))
             
        except Exception as e:
             self.lbl_status.config(text=f"Error: {e}", foreground=COLORS["error"])
             print(e)
             return []

    def set_loading(self, busy):
        # Legacy method kept/redirected or used by Save
        self.is_generating = busy
        if busy:
            self.progress.pack(fill=tk.X, pady=20)
            self.progress.start(10)
            self.lbl_status.config(text="Synthesizing...", foreground=COLORS["warning"])
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.lbl_status.config(text="Ready", foreground=COLORS["fg"])

    def generate_audio(self, phoneme_indices):
        """Run synthesis in a helper method (runs on thread). Returns raw bytes or None."""
        if not self.synthesizer:
            # Try to init again being lenient (maybe they added file)
            if os.path.exists(self.rom_path):
                 self.synthesizer = votrax.VotraxSC01A(self.rom_path)
            else:
                 # Fallback to dummy
                 self.synthesizer = votrax.VotraxSC01A(self.rom_path) # Logic inside handles missing file with dummy
        
        self.synthesizer.reset()
        
        all_samples = []
        for p_idx in phoneme_indices:
            if self.stop_requested: return None
            
            self.synthesizer.write_phone(p_idx)
            num_samples = self.synthesizer.get_phoneme_duration_samples()
            samples = self.synthesizer.generate_samples(num_samples)
            all_samples.append(samples)
            
        if not all_samples:
            return None
            
        final_wave = np.concatenate(all_samples)
        
        # Normalize
        max_val = np.max(np.abs(final_wave))
        if max_val > 0:
            final_wave = final_wave / max_val * 0.8 # Scale to 80%
            
        final_data = (final_wave * 32767).astype(np.int16)
        return final_data.tobytes()

    def on_play(self):
        # Toggle Logic
        if self.is_generating: 
            # Request Stop
            self.stop_requested = True
            winsound.PlaySound(None, winsound.SND_PURGE) # Stop playback if running
            self.lbl_status.config(text="Stopping...", foreground=COLORS["warning"])
            return
        
        indices = self.get_phonemes_from_input()
        if not indices:
            messagebox.showinfo("Info", "Please enter some text/phonemes first.")
            return

        self.stop_requested = False
        self.is_generating = True
        self.btn_play.set_text("STOP")
        self.progress.pack(fill=tk.X, pady=20)
        self.progress.start(10)

        def task():
            try:
                audio_bytes = self.generate_audio(indices)
                if self.stop_requested:
                    self.reset_ui_state()
                    return

                if audio_bytes:
                    # Create in-memory wav
                    import io
                    buf = io.BytesIO()
                    with wave.open(buf, 'wb') as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(int(self.synthesizer.sclock))
                        wav_file.writeframes(audio_bytes)
                    
                    wav_data = buf.getvalue()
                    
                    # Calculate duration for auto-reset
                    # Audio bytes size / (rate * 2 bytes)
                    # wav_data includes header, so rely on raw length roughly or audio_bytes
                    duration_sec = len(audio_bytes) / (int(self.synthesizer.sclock) * 2)
                    duration_ms = int(duration_sec * 1000)
                    
                    if self.stop_requested:
                        self.reset_ui_state()
                        return

                    # Play Async
                    self.lbl_status.config(text="Playing...", foreground=COLORS["success"])
                    winsound.PlaySound(wav_data, winsound.SND_MEMORY | winsound.SND_ASYNC)
                    
                    # Schedule Reset
                    self.after(duration_ms, self.reset_ui_state_if_playing)
                else:
                    self.lbl_status.config(text="No audio generated.", foreground=COLORS["error"])
                    self.reset_ui_state()

            except Exception as e:
                self.lbl_status.config(text=f"Error: {str(e)}", foreground=COLORS["error"])
                print(e)
                self.reset_ui_state()
        
        threading.Thread(target=task, daemon=True).start()

    def reset_ui_state(self):
        self.is_generating = False
        self.stop_requested = False
        self.btn_play.set_text("PLAY AUDIO")
        self.progress.stop()
        self.progress.pack_forget()
        self.lbl_status.config(text="Ready", foreground=COLORS["fg"])

    def reset_ui_state_if_playing(self):
        # Called by timer. Only reset if we haven't already been stopped/reset manually.
        # But here 'is_generating' flag covers "Playing" too in our logic.
        if self.is_generating and not self.stop_requested:
            self.reset_ui_state()

    def on_save(self):
        if self.is_generating: return
        
        indices = self.get_phonemes_from_input()
        if not indices:
            messagebox.showinfo("Info", "Please enter some text/phonemes first.")
            return
            
        path = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=[("WAV Audio", "*.wav")])
        if not path:
            return

        def task():
            self.set_loading(True)
            try:
                audio_bytes = self.generate_audio(indices)
                if audio_bytes:
                    with wave.open(path, 'wb') as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(int(self.synthesizer.sclock))
                        wav_file.writeframes(audio_bytes)
                    
                    self.lbl_status.config(text=f"Saved to {os.path.basename(path)}", foreground=COLORS["success"])
                    messagebox.showinfo("Success", f"Audio saved to {path}")
                else:
                    self.lbl_status.config(text="No audio generated.", foreground=COLORS["error"])

            except Exception as e:
                self.lbl_status.config(text=f"Error: {str(e)}", foreground=COLORS["error"])
                messagebox.showerror("Error", str(e))
            finally:
                self.set_loading(False)
        
        threading.Thread(target=task, daemon=True).start()

    def on_convert(self, *args):
        text = self.txt_english.get().strip()
        if not text:
            return
            
        self.lbl_status.config(text="Converting text...", foreground=COLORS["warning"])
        self.update() # Force redraw
        
        # Pre-process numbers (Simple 0-20 support to ensure "10" is spoken even if g2p fails to normalize)
        words = text.split()
        num_map = {
            "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
            "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
            "10": "ten", "11": "eleven", "12": "twelve"
        }
        for i, w in enumerate(words):
            if w in num_map:
                words[i] = num_map[w]
        text_norm = " ".join(words)

        try:
             # Lazy import
             try:
                 import nltk
                 from g2p_en import G2p
                 
                 # Ensure NLTK data is present
                 try:
                     try:
                        nltk.data.find('taggers/averaged_perceptron_tagger_eng')
                     except LookupError:
                        nltk.download('averaged_perceptron_tagger_eng', quiet=True)
                     
                     try:
                        nltk.data.find('corpora/cmudict')
                     except LookupError:
                        nltk.download('cmudict', quiet=True)
                 except Exception as e:
                     print(f"NLTK Download Warning: {e}")

             except ImportError:
                 messagebox.showerror("Missing Library", "g2p_en or nltk not found.\nPlease run: pip install g2p_en nltk")
                 self.lbl_status.config(text="Error: g2p_en missing", foreground=COLORS["error"])
                 return

             # Initialize model (takes time first run)
             if not hasattr(self, 'g2p_model'):
                 self.g2p_model = G2p()
                 
             arpabet_phones = self.g2p_model(text_norm)
             
             # Filter out non-alphanumeric (keep space?)
             # g2p returns list like ['HH', 'AH0', 'L', 'OW1', ' ', '...']
             
             votrax_phones = []
             for token in arpabet_phones:
                 # Clean token (remove stress digits for mapping lookup, but keeps them for nuanced mapping)
                 token_pure = ''.join([c for c in token if c.isalpha()])
                 token_stress = token[-1] if token[-1].isdigit() else None
                 
                 if token == ' ':
                     votrax_phones.append("PA1")
                     continue
                 if not token_pure: continue # Skip punctuation
                 
                 # The Map
                 # CMU -> Votrax SC01 Matches
                 # Diphthongs & Special Cases
                 if token_pure == "AY": 
                     # Eye (AH1 + Y1)
                     votrax_phones.extend(["AH1", "Y1"])
                 elif token_pure == "OW": 
                     # Go (O1 + U1)
                     votrax_phones.extend(["O1", "U1"])
                 elif token_pure == "OY": 
                     # Boy (O1 + I3)
                     votrax_phones.extend(["O1", "I3"])
                 elif token_pure == "AW": 
                     # Out (AH1 + U1 or AW2)
                     votrax_phones.extend(["AH1", "AW2"])
                 elif token_pure == "EY": 
                     # Day (A1 + Y)
                     votrax_phones.extend(["A1", "Y"])
                 elif token_pure == "IY": 
                     # See (E1 + Y)
                     votrax_phones.extend(["E1", "Y"])
                 elif token_pure == "UW": 
                     # You (IU + U1 or just U1)
                     votrax_phones.extend(["IU", "U1"])

                 # Simple Vowels
                 elif token_pure == "AA": votrax_phones.append("AH1" if token_stress == '1' else "A") 
                 elif token_pure == "AE": votrax_phones.append("AE1" if token_stress == '1' else "AE")
                 elif token_pure == "AH": votrax_phones.append("AH1" if token_stress == '1' else "AH")
                 elif token_pure == "AO": votrax_phones.append("AW1" if token_stress == '1' else "AW")
                 elif token_pure == "EH": votrax_phones.append("EH2" if token_stress == '1' else "EH3") # EH1 is very long, use EH2 for main stress
                 elif token_pure == "ER": votrax_phones.append("ER") 
                 elif token_pure == "IH": votrax_phones.append("I1" if token_stress == '1' else "I2")
                 elif token_pure == "UH": votrax_phones.append("OO1")
                 
                 # Consonants
                 elif token_pure == "B": votrax_phones.append("B")
                 elif token_pure == "CH": votrax_phones.append("CH")
                 elif token_pure == "D": votrax_phones.append("D")
                 elif token_pure == "DH": votrax_phones.append("THV")
                 elif token_pure == "F": votrax_phones.append("F")
                 elif token_pure == "G": votrax_phones.append("G")
                 elif token_pure == "HH": votrax_phones.append("H")
                 elif token_pure == "JH": votrax_phones.append("J")
                 elif token_pure == "K": votrax_phones.append("K")
                 elif token_pure == "L": votrax_phones.append("L")
                 elif token_pure == "M": votrax_phones.append("M")
                 elif token_pure == "N": votrax_phones.append("N")
                 elif token_pure == "NG": votrax_phones.append("NG")
                 elif token_pure == "P": votrax_phones.append("P")
                 elif token_pure == "R": votrax_phones.append("R")
                 elif token_pure == "S": votrax_phones.append("S")
                 elif token_pure == "SH": votrax_phones.append("SH")
                 elif token_pure == "T": votrax_phones.append("T")
                 elif token_pure == "TH": votrax_phones.append("TH")
                 elif token_pure == "V": votrax_phones.append("V")
                 elif token_pure == "W": votrax_phones.append("W")
                 elif token_pure == "Y": votrax_phones.append("Y")
                 elif token_pure == "Z": votrax_phones.append("Z")
                 elif token_pure == "ZH": votrax_phones.append("ZH")
                 else:
                     # Fallback
                     print(f"Unknown map for {token}, skipping")
                 
             # Update Text Box
             result_str = " ".join(votrax_phones)
             self.txt_input.delete("1.0", tk.END)
             self.txt_input.insert("1.0", result_str)
             self.lbl_status.config(text="Conversion complete", foreground=COLORS["success"])
             
        except Exception as e:
             self.lbl_status.config(text=f"Error: {e}", foreground=COLORS["error"])
             print(e)


if __name__ == "__main__":
    app = VotraxGUI()
    app.mainloop()
