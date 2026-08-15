#!/usr/bin/env python3
"""Quick mic test — prints RMS for 5 seconds. Triggers macOS TCC prompt."""
import time
import numpy as np
import sounddevice as sd

samples = []

def cb(indata, frames, time_info, status):
    rms = float(np.sqrt(np.mean(indata ** 2)))
    samples.append(rms)
    print(f"rms={rms:.4f}", flush=True)

with sd.InputStream(samplerate=44100, blocksize=4410, channels=1, dtype="float32", callback=cb):
    print("Listening 5s — make some noise / clap!", flush=True)
    time.sleep(5)

print(f"\nDONE. samples={len(samples)}, max_rms={max(samples) if samples else 0:.4f}")
