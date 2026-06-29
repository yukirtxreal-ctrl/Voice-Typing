#!/usr/bin/env python3
"""
First-run helper (called by setup.bat).

Detects whether your NVIDIA GPU can be used for speech recognition, picks the
best default model for your hardware, downloads it once, and writes config.json:
  - GPU available  -> model "large-v3" (most accurate), runs fast on the GPU
  - CPU only       -> model "small"    (fast and light on the CPU)
You can change the model any time inside the app.
"""

import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")


def detect_device():
    """Return ('cuda','float16') only if the GPU can actually load a model."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            from faster_whisper import WhisperModel
            # Verify the CUDA libraries (cuBLAS/cuDNN) really work.
            WhisperModel("tiny", device="cuda", compute_type="float16")
            return "cuda", "float16"
    except Exception as e:
        print("GPU not usable for speech (will use CPU):", e)
    return "cpu", "int8"


def main():
    device, compute = detect_device()
    model = "large-v3" if device == "cuda" else "small"
    print("=" * 56)
    print("  Hardware: %s   ->   default model: %s" % (device.upper(), model))
    print("=" * 56)

    from faster_whisper import WhisperModel
    print("Downloading model '%s' (one-time)…" % model)
    try:
        WhisperModel(model)  # downloads the model files into the cache
    except Exception as e:
        print("Could not pre-download '%s' (%s); falling back to 'small'." % (model, e))
        model = "small"
        WhisperModel("small")

    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    cfg["device"] = device
    cfg["compute"] = compute
    cfg.setdefault("model", model)        # keep a model the user already chose
    cfg.setdefault("language", "auto")
    cfg.setdefault("mic_device", "default")
    cfg.setdefault("hotkey", "Alt+Up")
    cfg.setdefault("trailing_space", True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print("Saved settings to config.json")


if __name__ == "__main__":
    main()
