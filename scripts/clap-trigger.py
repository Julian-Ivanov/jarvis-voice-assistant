#!/usr/bin/env python3
"""
Jarvis — Double Clap Trigger
Listens to mic. Detects two claps within 1.2s, min 0.1s apart.
On trigger: runs scripts/launch-session.ps1 then exits.
"""

import sounddevice as sd
import numpy as np
import subprocess
import time
import os
import json

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

WORKSPACE_PATH = config["workspace_path"]
SCRIPT_PATH = os.path.join(WORKSPACE_PATH, "scripts", "launch-session.ps1")

SAMPLE_RATE = 44100
BLOCK_SIZE = 512
THRESHOLD = 0.03       # RMS volume spike threshold — lower = more sensitive
MIN_GAP = 0.05         # Minimum seconds between claps
MAX_GAP = 1.5          # Maximum seconds between claps — more time for second clap
COOLDOWN = 3.0         # Seconds to ignore after trigger fires

last_clap_time = 0.0
triggered = False

def audio_callback(indata, frames, time_info, status):
    global last_clap_time, triggered

    if triggered:
        return

    now = time.time()
    rms = float(np.sqrt(np.mean(indata ** 2)))

    if rms > THRESHOLD:
        gap = now - last_clap_time

        if gap >= MIN_GAP:
            if gap <= MAX_GAP and last_clap_time > 0:
                # Second clap — fire trigger and shut down
                print(f"[jarvis] Double clap detected! Firing launch script. Shutting down.", flush=True)
                triggered = True
                last_clap_time = 0.0
                subprocess.Popen(["powershell", "-ExecutionPolicy", "Bypass", "-File", SCRIPT_PATH])
            else:
                # First clap
                print(f"[jarvis] First clap detected (rms={rms:.3f})", flush=True)
                last_clap_time = now

with sd.InputStream(
    samplerate=SAMPLE_RATE,
    blocksize=BLOCK_SIZE,
    channels=1,
    dtype="float32",
    callback=audio_callback,
):
    print("[jarvis] Listening for double clap...", flush=True)
    while not triggered:
        time.sleep(0.1)
    print("[jarvis] Trigger fired — stopped listening.", flush=True)
