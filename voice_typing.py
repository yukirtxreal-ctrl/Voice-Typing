#!/usr/bin/env python3
"""
Voice Typing - a desktop dictation app for Windows.

Click into any text field (browser, Word, chat, code editor - anywhere), then
press the global hotkey (default Alt+Up) or the on-screen mic button, and talk.
Your speech is transcribed locally with Whisper (free, offline, private) and
typed wherever your cursor is. Pick your spoken language, microphone and model
right in the app. Settings are saved automatically.

It automatically uses your NVIDIA GPU when available (much faster), so you can
run the most accurate model (large-v3); otherwise it runs on the CPU.
"""

import os
import sys
import json
import math
import threading
import queue
import time

FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    HERE = os.path.dirname(sys.executable)        # writable files (config/log)
    RES_DIR = getattr(sys, "_MEIPASS", HERE)      # bundled assets (icons)
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
    RES_DIR = HERE
CONFIG_PATH = os.path.join(HERE, "config.json")
LOG_PATH = os.path.join(HERE, "voice_typing.log")

# When launched with pythonw.exe there is no console; route output to a log file
# so nothing crashes on print() and errors are still recoverable.
if sys.stdout is None:
    try:
        sys.stdout = open(LOG_PATH, "a", encoding="utf-8")
    except Exception:
        sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = sys.stdout

# ----------------------------- palette --------------------------------------
BG       = "#0B0B0F"   # near-black window
PANEL    = "#121218"   # cards
PANEL2   = "#1A1A23"   # inputs
ACCENT   = "#8B6CFF"   # purple (matches the logo)
ACCENT2  = "#B9A4FF"   # light purple
TEXT     = "#ECECF2"
SUB      = "#8A8A99"
GOOD     = "#54E3A8"

# ------------------------- languages & models -------------------------------
LANGUAGES = [
    ("Auto-detect", "auto"), ("English", "en"), ("Spanish", "es"),
    ("French", "fr"), ("German", "de"), ("Italian", "it"),
    ("Portuguese", "pt"), ("Dutch", "nl"), ("Russian", "ru"),
    ("Chinese", "zh"), ("Japanese", "ja"), ("Korean", "ko"),
    ("Arabic", "ar"), ("Hindi", "hi"), ("Turkish", "tr"),
    ("Polish", "pl"), ("Ukrainian", "uk"), ("Vietnamese", "vi"),
    ("Indonesian", "id"), ("Thai", "th"), ("Tagalog", "tl"),
]
CODE_TO_NAME = {c: n for n, c in LANGUAGES}
NAME_TO_CODE = {n: c for n, c in LANGUAGES}

# multilingual whisper models, worst->best accuracy
MODELS = ["small", "medium", "large-v3"]
MODEL_HINT = {"small": "fast", "medium": "accurate", "large-v3": "best"}

HOTKEYS = ["Alt+Up", "Alt+Down", "F9", "F8", "Ctrl+Space", "Alt+Space"]
def hotkey_to_kb(label):
    return label.lower().replace(" ", "")  # "Ctrl+Space" -> "ctrl+space"

# LanguageTool locale codes for the grammar fixer (subset; others default en-US)
GRAMMAR_LANG = {
    "auto": "en-US", "en": "en-US", "es": "es", "fr": "fr", "de": "de-DE",
    "it": "it", "pt": "pt-PT", "nl": "nl", "ru": "ru-RU", "pl": "pl-PL",
    "uk": "uk-UA",
}

# Phrases Whisper commonly hallucinates on silence/noise. Dropped only when they
# are the ENTIRE output (so a real sentence containing them is unaffected).
HALLUCINATIONS = {
    "thank you", "thank you very much", "thanks for watching",
    "thank you for watching", "please subscribe", "subscribe", "you",
}


def _norm_hallu(s):
    return s.strip().lower().strip(" .,!?\"'").strip()

DEFAULTS = {
    "language": "auto",
    "model": "small",
    "mic_device": "default",   # "default" or a microphone name
    "hotkey": "Alt+Up",
    "trailing_space": True,
    "grammar": False,          # fix grammar/spelling before typing
    "device": "auto",          # "auto" | "cuda" | "cpu"
    "compute": "auto",
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def best_device_light():
    """Quick check: use CUDA (GPU) if CTranslate2 reports a device, else CPU.
    Actual load failures fall back to CPU at model-load time."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def add_cuda_dll_dirs():
    """Help CTranslate2 find cuBLAS/cuDNN DLLs from the pip nvidia-* wheels."""
    try:
        import os, sys
        base = os.path.join(sys.prefix, "Lib", "site-packages", "nvidia")
        for sub in ("cublas", "cudnn", "cuda_runtime"):
            d = os.path.join(base, sub, "bin")
            if os.path.isdir(d):
                try:
                    os.add_dll_directory(d)
                except Exception:
                    pass
    except Exception:
        pass


AUTO_MIC = "Automatic (current mic)"


def input_device_info(index):
    """(name, index) for an input device, or the live system default if None."""
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        try:
            info = (pa.get_device_info_by_index(index) if index is not None
                    else pa.get_default_input_device_info())
            return info.get("name"), int(info.get("index"))
        finally:
            pa.terminate()
    except Exception:
        return None, None


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def blend(c1, c2, t):
    a, b = hex2rgb(c1), hex2rgb(c2)
    r = tuple(max(0, min(255, int(a[i] * t + b[i] * (1 - t)))) for i in range(3))
    return "#%02x%02x%02x" % r


# --------------------------- early CLI path ---------------------------------
def list_mics_cli():
    try:
        import speech_recognition as sr
        names = sr.Microphone.list_microphone_names()
        print("Available microphones:")
        for i, n in enumerate(names):
            print("  [%d] %s" % (i, n))
    except Exception as e:
        print("Could not list microphones:", e)


# ============================ speech engine =================================
class Engine:
    """Owns the Whisper model, the microphone, and the listening loop."""

    def __init__(self, emit):
        self.emit = emit                 # emit(kind, payload) -> UI queue
        self.model = None
        self.model_name = None
        self.recognizer = None
        self.mic = None
        self.device_index = None
        self.language = "auto"
        self.trailing_space = True
        self.fix_grammar = False
        self._lt = None            # LanguageTool instance (lazy)
        self._lt_mode = None       # "offline" | "online"
        self._lt_lang = None
        self.device = "cpu"
        self.compute = "int8"
        self.listening = False
        self._stop = None
        self._lock = threading.Lock()

    # ---- setup -------------------------------------------------------------
    def init_mic(self, device_index):
        import speech_recognition as sr
        self.device_index = device_index
        self.mic = sr.Microphone(device_index=device_index, sample_rate=16000)
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8
        self.recognizer.dynamic_energy_threshold = True
        with self.mic as src:
            self.recognizer.adjust_for_ambient_noise(src, duration=0.8)

    def load_model(self, name):
        add_cuda_dll_dirs()
        from faster_whisper import WhisperModel
        import numpy as np
        probe = np.zeros(4000, dtype=np.float32)
        attempts = []
        if self.device == "cuda":
            attempts.append(("cuda", "float16", name))
        # On CPU the big models are too slow, so fall back to a fast one.
        cpu_model = "small" if name in ("large-v3", "large-v2", "medium") else name
        attempts.append(("cpu", "int8", cpu_model))
        last_err = None
        for dev, comp, use in attempts:
            try:
                self.emit("status", "Loading %s on %s…" % (use, dev.upper()))
                m = WhisperModel(use, device=dev, compute_type=comp)
                list(m.transcribe(probe, language="en")[0])  # confirm inference runs
                self.model = m
                self.device, self.compute, self.model_name = dev, comp, use
                self.emit("status", "Ready • %s on %s" % (use, dev.upper()))
                print("[VT] model ok: %s on %s" % (use, dev), flush=True)
                return
            except Exception as e:
                last_err = e
                print("[VT] load/infer failed (%s on %s): %s" % (use, dev, e),
                      flush=True)
        raise RuntimeError("model load failed: %s" % last_err)

    # ---- transcription -----------------------------------------------------
    def _transcribe(self, audio):
        import numpy as np
        raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        # Skip near-silence: stops hallucinated filler on quiet/no-speech audio.
        if data.size == 0 or float(np.sqrt(np.mean(data ** 2))) < 0.0015:
            return ""
        lang = None if self.language == "auto" else self.language
        segments, _info = self.model.transcribe(
            data, language=lang, beam_size=5,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            condition_on_previous_text=False,
        )
        parts = []
        for s in segments:
            # Drop segments Whisper itself flags as silence / low-confidence.
            if getattr(s, "no_speech_prob", 0.0) > 0.6:
                continue
            if getattr(s, "avg_logprob", 0.0) < -1.0:
                continue
            parts.append(s.text)
        text = "".join(parts).strip()
        # Final guard: drop output that is ONLY a known hallucination phrase.
        if _norm_hallu(text) in HALLUCINATIONS:
            return ""
        return text

    def _on_phrase(self, _rec, audio):
        if not self.listening:
            return
        self.emit("status", "Transcribing…")
        try:
            text = self._transcribe(audio)
        except Exception as e:
            print("[VT] transcribe error: %s" % e, flush=True)
            self.emit("status", "Error: %s" % e)
            return
        if text and self.fix_grammar:
            text = self._grammar_fix(text)
        if text:
            try:
                import keyboard
                keyboard.write(text + (" " if self.trailing_space else ""))
            except Exception as e:
                print("[VT] type error: %s" % e, flush=True)
                self.emit("status", "Typing error: %s" % e)
            self.emit("text", text)
        if self.listening:
            self.emit("status", "Listening…")

    # ---- control -----------------------------------------------------------
    def start(self):
        with self._lock:
            if self.listening or self.model is None or self.recognizer is None:
                return
            self.listening = True
        try:
            import speech_recognition as sr
            # Fresh mic handle each session avoids the
            # "already inside a context manager" race.
            self.mic = sr.Microphone(device_index=self.device_index,
                                     sample_rate=16000)
            self._stop = self.recognizer.listen_in_background(
                self.mic, self._on_phrase, phrase_time_limit=15)
        except Exception as e:
            self.listening = False
            self.emit("state", False)
            self.emit("status", "Mic error: %s" % e)
            print("[VT] start error: %s" % e, flush=True)
            return
        self.emit("state", True)
        self.emit("status", "Listening…")

    def stop(self):
        with self._lock:
            if not self.listening:
                return
            self.listening = False
        if self._stop:
            try:
                self._stop(wait_for_stop=False)
            except Exception:
                pass
            self._stop = None
        self.emit("state", False)
        self.emit("status", "Ready")

    def toggle(self):
        self.stop() if self.listening else self.start()

    # ---- grammar fixing ----------------------------------------------------
    def prepare_grammar(self):
        """Set up the grammar engine. Runs in a background thread.
        Prefers OFFLINE LanguageTool (unlimited & private) using a bundled Java,
        and falls back to the free online API only if that can't start."""
        want = GRAMMAR_LANG.get(self.language, "en-US")
        if self._lt is not None and self._lt_lang == want:
            return
        self.emit("status", "Setting up grammar…")
        try:
            import language_tool_python
        except Exception:
            if FROZEN:
                self._lt = None
                self.emit("status", "Grammar unavailable")
                return
            try:
                import subprocess
                self.emit("status", "Installing grammar support…")
                subprocess.check_call([sys.executable, "-m", "pip", "install",
                                       "language_tool_python"])
                import language_tool_python
            except Exception as e:
                self._lt = None
                self.emit("status", "Grammar unavailable")
                print("[VT] grammar pkg install failed: %s" % e, flush=True)
                return
        self._ensure_java()
        lt, mode = None, None
        try:
            self.emit("status", "Starting offline grammar (first run downloads it)…")
            lt = language_tool_python.LanguageTool(want)
            mode = "offline"
        except Exception as e:
            print("[VT] offline grammar failed (%s); trying online" % e, flush=True)
            try:
                lt = language_tool_python.LanguageToolPublicAPI(want)
                mode = "online"
            except Exception as e2:
                print("[VT] online grammar failed: %s" % e2, flush=True)
        if lt is None:
            self._lt = None
            self.emit("status", "Grammar unavailable")
            return
        self._lt, self._lt_mode, self._lt_lang = lt, mode, want
        self.emit("status", "Grammar ready (%s)" % mode)
        print("[VT] grammar ready: %s (%s)" % (want, mode), flush=True)

    def _ensure_java(self):
        """Provide a Java runtime (bundled via jdk4py) so LanguageTool can run
        offline without the user installing anything."""
        import os, shutil
        if shutil.which("java") or os.path.isdir(
                os.path.join(os.environ.get("JAVA_HOME", "x"), "bin")):
            return
        try:
            import jdk4py
        except Exception:
            if FROZEN:
                return
            try:
                import subprocess
                self.emit("status", "Downloading offline grammar engine (one-time)…")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "jdk4py"])
                import jdk4py
            except Exception as e:
                print("[VT] jdk4py install failed: %s" % e, flush=True)
                return
        try:
            jh = str(jdk4py.JAVA_HOME)
            os.environ["JAVA_HOME"] = jh
            os.environ["PATH"] = (os.path.join(jh, "bin") + os.pathsep
                                  + os.environ.get("PATH", ""))
            print("[VT] bundled Java at %s" % jh, flush=True)
        except Exception as e:
            print("[VT] jdk4py setup failed: %s" % e, flush=True)

    def _grammar_fix(self, text):
        lt = self._lt
        if not lt:
            return text
        try:
            fixed = lt.correct(text)
            return fixed if fixed else text
        except Exception as e:
            print("[VT] grammar correct error: %s" % e, flush=True)
            return text


# =============================== the app ====================================
def build_app():
    import customtkinter as ctk
    import tkinter as tk
    from tkinter import messagebox
    from PIL import Image

    ctk.set_appearance_mode("dark")

    class App(ctk.CTk):
        def __init__(self):
            super().__init__()
            self.cfg = load_config()
            self.q = queue.Queue()
            self.engine = Engine(self._emit)
            self.engine.language = self.cfg.get("language", "auto")
            self.engine.trailing_space = self.cfg.get("trailing_space", True)
            self.engine.fix_grammar = self.cfg.get("grammar", False)

            # resolve compute device (GPU/CPU)
            dev = self.cfg.get("device", "auto")
            if dev in ("cuda", "cpu"):
                self.device = dev
                self.compute = self.cfg.get(
                    "compute", "float16" if dev == "cuda" else "int8")
            else:
                self.device, self.compute = best_device_light()
            self.engine.device = self.device
            self.engine.compute = self.compute

            # first run with a GPU -> default to the best model
            if not os.path.exists(CONFIG_PATH):
                self.cfg["model"] = "large-v3" if self.device == "cuda" else "small"
                save_config(self.cfg)

            self.ready = False
            self.active = False
            self._hotkey_handle = None

            self.title("Voice Typing")
            self.configure(fg_color=BG)
            self.resizable(False, True)
            self._center(470, 900)
            self.minsize(470, 560)

            self.f_title = ctk.CTkFont("Segoe UI Semibold", 22)
            self.f_body  = ctk.CTkFont("Segoe UI", 14)
            self.f_small = ctk.CTkFont("Segoe UI", 12)
            self.f_tiny  = ctk.CTkFont("Segoe UI", 11)
            self.f_status = ctk.CTkFont("Segoe UI", 13)

            self._last_default_idx = None
            self._build()
            self._apply_icon()
            self.after(300, self._apply_icon)
            self.after(1200, self._apply_icon)
            self.protocol("WM_DELETE_WINDOW", self._on_close)
            self.after(60, self._poll)
            self.after(80, self._animate)
            self.after(1500, self._refresh_mic_label)
            threading.Thread(target=self._startup, daemon=True).start()

        # ---- layout --------------------------------------------------------
        def _center(self, w, h):
            sw = self.winfo_screenwidth()
            x = max(0, int(sw / 2 - w / 2))
            self.geometry("%dx%d+%d+%d" % (w, h, x, 20))

        def _apply_icon(self):
            # Window + taskbar icon. iconphoto(PNG) is the reliable path; the
            # .ico is best-effort. Called a few times to beat customtkinter's
            # own icon, which it sets shortly after the window is created.
            try:
                ico = os.path.join(RES_DIR, "app.ico")
                if os.path.exists(ico):
                    self.iconbitmap(ico)
            except Exception:
                pass
            try:
                from PIL import Image, ImageTk
                # Bold icon for the window/taskbar so it stays crisp when tiny.
                png = os.path.join(RES_DIR, "icon_small.png")
                if not os.path.exists(png):
                    png = os.path.join(RES_DIR, "logo.png")
                src = Image.open(png)
                self._icon_imgs = [
                    ImageTk.PhotoImage(src.resize((s, s), Image.LANCZOS))
                    for s in (16, 24, 32, 48, 64)]
                self.iconphoto(True, *self._icon_imgs)
            except Exception:
                pass

        def _build(self):
            head = ctk.CTkFrame(self, fg_color="transparent")
            head.pack(fill="x", padx=22, pady=(18, 4))
            try:
                img = Image.open(os.path.join(RES_DIR, "logo.png"))
                self.logo = ctk.CTkImage(light_image=img, dark_image=img, size=(46, 46))
                ctk.CTkLabel(head, image=self.logo, text="").pack(side="left")
            except Exception:
                pass
            box = ctk.CTkFrame(head, fg_color="transparent")
            box.pack(side="left", padx=12)
            ctk.CTkLabel(box, text="Voice Typing", text_color=TEXT,
                         font=self.f_title).pack(anchor="w")
            ctk.CTkLabel(box, text="speak → type anywhere",
                         text_color=SUB, font=self.f_small).pack(anchor="w")

            self.canvas = tk.Canvas(self, width=460, height=250, bg=BG,
                                    highlightthickness=0, bd=0)
            self.canvas.pack(pady=(6, 0))
            self.canvas.bind("<Button-1>", self._canvas_click)

            self.hint = ctk.CTkLabel(
                self, text="Click where you want to type, then press %s"
                % self.cfg.get("hotkey", "Alt+Up"),
                text_color=SUB, font=self.f_small)
            self.hint.pack(pady=(0, 2))

            self.status_card = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=14)
            self.status_card.pack(fill="x", padx=22, pady=(6, 8))
            self.status = ctk.CTkLabel(self.status_card, text="Starting…",
                                       text_color=ACCENT2, font=self.f_status)
            self.status.pack(padx=14, pady=10, anchor="w")
            self.last = ctk.CTkLabel(self.status_card, text="", text_color=SUB,
                                     font=self.f_small, wraplength=380,
                                     justify="left", anchor="w")

            card = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=16)
            card.pack(fill="x", padx=22, pady=(2, 10))
            ctk.CTkLabel(card, text="SETTINGS", text_color=SUB,
                         font=self.f_tiny).pack(anchor="w", padx=16, pady=(12, 2))

            self.lang_menu = self._menu(
                card, "Language", [n for n, _ in LANGUAGES],
                CODE_TO_NAME.get(self.cfg.get("language", "auto"), "Auto-detect"),
                self._on_language)

            self.mic_menu = self._menu(
                card, "Microphone", self._mic_values(),
                self._mic_initial(), self._on_mic)
            self.using_label = ctk.CTkLabel(
                card, text="Using: detecting…", text_color=ACCENT2,
                font=self.f_tiny)
            self.using_label.pack(anchor="w", padx=18, pady=(0, 4))

            self.model_menu = self._menu(
                card, "Accuracy model",
                ["%s  (%s)" % (m, MODEL_HINT[m]) for m in MODELS],
                self._model_label(self.cfg.get("model", "small")),
                self._on_model)

            self.hotkey_menu = self._menu(
                card, "Global hotkey", HOTKEYS,
                self.cfg.get("hotkey", "Alt+Up"), self._on_hotkey)

            grow = ctk.CTkFrame(card, fg_color="transparent")
            grow.pack(fill="x", padx=16, pady=(12, 2))
            self.grammar_switch = ctk.CTkSwitch(
                grow, text="Fix grammar & spelling", command=self._on_grammar,
                progress_color=ACCENT, text_color=TEXT, font=self.f_body)
            if self.cfg.get("grammar", False):
                self.grammar_switch.select()
            self.grammar_switch.pack(anchor="w")
            ctk.CTkLabel(grow, text="Tidies each sentence before it's typed",
                         text_color=SUB, font=self.f_tiny).pack(anchor="w",
                                                                 pady=(2, 0))

            ctk.CTkLabel(card, text="", height=4, fg_color="transparent").pack()

            ctk.CTkLabel(
                self, text="Runs offline • your voice never leaves this PC",
                text_color=SUB, font=self.f_tiny).pack(pady=(0, 12))

        def _menu(self, parent, label, values, initial, command):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=(6, 2))
            ctk.CTkLabel(row, text=label, text_color=SUB,
                         font=self.f_small).pack(anchor="w")
            om = ctk.CTkOptionMenu(
                row, values=values, command=command,
                fg_color=PANEL2, button_color="#252533",
                button_hover_color=ACCENT, text_color=TEXT,
                dropdown_fg_color=PANEL2, dropdown_text_color=TEXT,
                dropdown_hover_color=ACCENT, font=self.f_body,
                corner_radius=10, height=38)
            om.set(initial)
            om.pack(fill="x", pady=(4, 0))
            return om

        # ---- mic helpers ---------------------------------------------------
        def _mic_names(self):
            try:
                import speech_recognition as sr
                return list(sr.Microphone.list_microphone_names())
            except Exception:
                return []

        def _mic_values(self):
            return [AUTO_MIC] + self._mic_names()

        def _mic_initial(self):
            d = self.cfg.get("mic_device", "default")
            if d == "default":
                return AUTO_MIC
            return d if d in self._mic_names() else AUTO_MIC

        def _resolve_device(self, value):
            if value == AUTO_MIC:
                return None
            names = self._mic_names()
            if value in names:
                return names.index(value)
            for i, n in enumerate(names):
                if value.lower() in n.lower():
                    return i
            return None

        def _model_label(self, m):
            return "%s  (%s)" % (m, MODEL_HINT.get(m, ""))

        def _active_input(self):
            idx = self.engine.device_index
            if idx is None:
                return input_device_info(None)
            names = self._mic_names()
            name = names[idx] if 0 <= idx < len(names) else None
            return name, idx

        def _refresh_mic_label(self):
            try:
                name, idx = self._active_input()
                if name:
                    self.using_label.configure(text="Using: %s" % name)
                # In automatic mode, follow the system default if it changes.
                if (self.engine.device_index is None and idx is not None
                        and not self.engine.listening):
                    if self._last_default_idx is None:
                        self._last_default_idx = idx
                    elif idx != self._last_default_idx:
                        self._last_default_idx = idx
                        threading.Thread(target=self._reinit_mic,
                                         args=(AUTO_MIC,), daemon=True).start()
            except Exception:
                pass
            self.after(3000, self._refresh_mic_label)

        # ---- startup / model loading --------------------------------------
        def _startup(self):
            try:
                self._emit("status", "Preparing microphone…")
                self.engine.init_mic(self._resolve_device(self._mic_initial()))
            except Exception as e:
                self._emit("fatal",
                           "No microphone found, or PyAudio isn't installed.\n\n"
                           "Connect a mic (or headset) and reopen the app.\n\n%s" % e)
                return
            try:
                self.engine.load_model(self.cfg.get("model", "small"))
            except Exception as e:
                self._emit("fatal", "Could not load the speech model.\n\n%s" % e)
                return
            # Remember the device that actually worked (skip a broken GPU next time).
            self.cfg["device"] = self.engine.device
            self.cfg["compute"] = self.engine.compute
            save_config(self.cfg)
            self._register_hotkey(self.cfg.get("hotkey", "Alt+Up"))
            print("[VoiceTyping] model ready: %s on %s"
                  % (self.engine.model_name, self.engine.device), flush=True)
            self._emit("ready", None)
            if self.engine.fix_grammar:
                threading.Thread(target=self.engine.prepare_grammar,
                                 daemon=True).start()

        # ---- hotkey --------------------------------------------------------
        def _register_hotkey(self, label):
            try:
                import keyboard
            except Exception:
                return
            try:
                if self._hotkey_handle is not None:
                    keyboard.remove_hotkey(self._hotkey_handle)
            except Exception:
                pass
            try:
                self._hotkey_handle = keyboard.add_hotkey(
                    hotkey_to_kb(label), self.engine.toggle)
            except Exception:
                self._hotkey_handle = None

        # ---- events --------------------------------------------------------
        def _canvas_click(self, event):
            if not self.ready:
                return
            if (event.x - 230) ** 2 + (event.y - 114) ** 2 <= 84 ** 2:
                self.engine.toggle()

        def _on_language(self, name):
            self.engine.language = NAME_TO_CODE.get(name, "auto")
            self.cfg["language"] = self.engine.language
            save_config(self.cfg)

        def _on_hotkey(self, label):
            self.cfg["hotkey"] = label
            save_config(self.cfg)
            self._register_hotkey(label)
            self.hint.configure(
                text="Click where you want to type, then press %s" % label)

        def _on_grammar(self):
            on = bool(self.grammar_switch.get())
            self.engine.fix_grammar = on
            self.cfg["grammar"] = on
            save_config(self.cfg)
            if on:
                threading.Thread(target=self.engine.prepare_grammar,
                                 daemon=True).start()

        def _on_mic(self, value):
            self.cfg["mic_device"] = "default" if value == AUTO_MIC else value
            save_config(self.cfg)
            threading.Thread(target=self._reinit_mic,
                             args=(value,), daemon=True).start()

        def _reinit_mic(self, value):
            was = self.engine.listening
            if was:
                self.engine.stop()
            self._emit("status", "Switching microphone…")
            try:
                self.engine.init_mic(self._resolve_device(value))
                self._emit("status", "Listening…" if was else "Ready")
                if was:
                    self.engine.start()
            except Exception as e:
                self._emit("status", "Mic error: %s" % e)

        def _on_model(self, label):
            model = label.split()[0]
            self.cfg["model"] = model
            save_config(self.cfg)
            threading.Thread(target=self._reload_model,
                             args=(model,), daemon=True).start()

        def _reload_model(self, model):
            was = self.engine.listening
            if was:
                self.engine.stop()
            self.ready = False
            try:
                self.engine.load_model(model)
                self._emit("ready", None)
                if was:
                    self.engine.start()
            except Exception as e:
                self._emit("status", "Model error: %s" % e)

        # ---- queue from threads -------------------------------------------
        def _emit(self, kind, payload=None):
            self.q.put((kind, payload))

        def _poll(self):
            try:
                while True:
                    kind, payload = self.q.get_nowait()
                    if kind == "status":
                        self.status.configure(text=payload)
                    elif kind == "state":
                        self.active = bool(payload)
                        self.status.configure(
                            text_color=GOOD if self.active else ACCENT2)
                    elif kind == "text":
                        self.last.configure(text="“" + payload + "”")
                        if not self.last.winfo_ismapped():
                            self.last.pack(padx=14, pady=(0, 10), anchor="w")
                    elif kind == "ready":
                        self.ready = True
                    elif kind == "fatal":
                        try:
                            messagebox.showerror("Voice Typing", payload)
                        except Exception:
                            pass
                        self.status.configure(text="Setup needed - see message",
                                              text_color="#FF6B6B")
            except queue.Empty:
                pass
            self.after(60, self._poll)

        # ---- animation -----------------------------------------------------
        def _animate(self):
            try:
                self._draw()
            except Exception:
                pass
            # ~33 fps while listening (smooth); idle is static so redraw slowly.
            self.after(30 if self.active else 150, self._animate)

        def _power_glyph(self, cx, cy, color):
            # Universal power on/off symbol: a broken ring with a vertical bar.
            c = self.canvas
            r = 27
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=115, extent=310,
                         style="arc", outline=color, width=6)
            c.create_line(cx, cy - r - 4, cx, cy + 3, fill=color, width=6,
                          capstyle="round")

        def _draw(self):
            c = self.canvas
            c.delete("all")
            cx, cy, R = 230, 114, 56
            active = self.active
            # Smooth sonar ripples: rings continuously emanate outward and fade.
            # Time-based so the speed is constant regardless of frame rate.
            if active:
                now = time.time()
                for k in range(4):
                    frac = (now * 0.55 + k / 4.0) % 1.0
                    rr = R + 4 + frac * 50
                    col = blend(ACCENT, BG, 0.6 * (1.0 - frac) ** 1.4)
                    c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                                  outline=col, width=3)
                # gentle breathing on the outer track ring
                glow = 0.5 + 0.5 * math.sin(now * 3.0)
                track = blend(ACCENT2, BG, 0.45 + 0.35 * glow)
            else:
                track = "#2C2740"
            c.create_oval(cx - R - 9, cy - R - 9, cx + R + 9, cy + R + 9,
                          outline=track, width=2)
            c.create_oval(cx - R, cy - R, cx + R, cy + R,
                          fill=(ACCENT if active else "#191922"),
                          outline=(ACCENT2 if active else "#3A3350"), width=3)
            self._power_glyph(cx, cy, "#FFFFFF" if active else "#7B7B92")
            c.create_text(cx, 236,
                          text=("●  LISTENING" if active else "TAP TO TALK"),
                          fill=(GOOD if active else "#6E6E84"),
                          font=("Segoe UI", 11, "bold"))

        # ---- close ---------------------------------------------------------
        def _on_close(self):
            try:
                self.engine.stop()
            except Exception:
                pass
            try:
                if self.engine._lt is not None:
                    self.engine._lt.close()   # stop the grammar (Java) server
            except Exception:
                pass
            try:
                import keyboard
                keyboard.unhook_all()
            except Exception:
                pass
            self.destroy()
            os._exit(0)

    return App


def main():
    if "--list-mics" in sys.argv or "-l" in sys.argv:
        list_mics_cli()
        return
    # Make Windows treat this as its own app so the taskbar uses our icon.
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(u"VoiceTyping.App")
    except Exception:
        pass
    try:
        App = build_app()
    except Exception as e:
        try:
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk(); r.withdraw()
            messagebox.showerror(
                "Voice Typing",
                "A required component is missing. Please run setup.bat first.\n\n%s" % e)
        except Exception:
            print("Missing components - run setup.bat. (%s)" % e)
        return
    App().mainloop()


if __name__ == "__main__":
    main()
