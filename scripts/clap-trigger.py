#!/usr/bin/env python3
"""
Jarvis — Double Clap Trigger
Listens to mic. Detects two claps within 1.2s, min 0.1s apart.
On trigger: runs the platform-appropriate launch script, then exits.
"""

import json
import os
import platform
import subprocess
import time

import numpy as np
import sounddevice as sd

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

WORKSPACE_PATH = config["workspace_path"]

IS_MAC = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"

if IS_MAC:
    SCRIPT_PATH = os.path.join(WORKSPACE_PATH, "scripts", "launch-session.sh")
    LAUNCH_CMD = ["bash", SCRIPT_PATH]
elif IS_WINDOWS:
    SCRIPT_PATH = os.path.join(WORKSPACE_PATH, "scripts", "launch-session.ps1")
    LAUNCH_CMD = ["powershell", "-ExecutionPolicy", "Bypass", "-File", SCRIPT_PATH]
else:
    SCRIPT_PATH = os.path.join(WORKSPACE_PATH, "scripts", "launch-session.sh")
    LAUNCH_CMD = ["bash", SCRIPT_PATH]

SAMPLE_RATE = 44100
BLOCK_SIZE = 1024
THRESHOLD = 0.015      # RMS volume spike threshold — lower = more sensitive
MIN_GAP = 0.05         # Minimum seconds between claps
MAX_GAP = 2.0          # Maximum seconds between claps — more time for second clap
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
                # Second clap — set flag; main loop spawns the launcher to keep audio thread responsive
                print(f"[jarvis] Double clap detected! Firing launch script.", flush=True)
                triggered = True
                last_clap_time = 0.0
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
    while True:
        if triggered:
            subprocess.Popen(LAUNCH_CMD, start_new_session=True)
            print(f"[jarvis] Launcher spawned — cooldown {COOLDOWN}s then re-arming.", flush=True)
            time.sleep(COOLDOWN)
            triggered = False
            last_clap_time = 0.0
            print("[jarvis] Re-armed. Listening for double clap...", flush=True)
        time.sleep(0.1)
