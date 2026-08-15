#!/usr/bin/env python3
"""15-second mic diagnostic for launchd context. Writes RMS samples to log."""
import time
import numpy as np
import sounddevice as sd

print(f"[diag] default input: {sd.query_devices(kind='input')['name']}", flush=True)

peak = 0.0
count = 0

def cb(indata, frames, t, s):
    global peak, count
    r = float(np.sqrt(np.mean(indata ** 2)))
    count += 1
    if r > peak:
        peak = r
    if count % 10 == 0:
        print(f"[diag] sample#{count} rms={r:.5f} peak={peak:.5f}", flush=True)

with sd.InputStream(samplerate=44100, blocksize=4410, channels=1, dtype="float32", callback=cb):
    print("[diag] stream open, listening 15s...", flush=True)
    time.sleep(15)

print(f"[diag] DONE. samples={count} peak_rms={peak:.5f}", flush=True)
if peak < 0.0001:
    print("[diag] VERDICT: silence — launchd does NOT have mic access (TCC blocked)", flush=True)
else:
    print("[diag] VERDICT: receiving audio — TCC is fine", flush=True)
