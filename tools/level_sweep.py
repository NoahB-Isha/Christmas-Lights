#!/usr/bin/env python3
"""level_sweep.py -- audio-box characterisation: a steady tone stepping up in
level, 10 s per step with 1 s of silence between, same on both channels.
Watch which scene (ladder card) / brightness each step produces.

    python3 tools/level_sweep.py out/level_sweep.wav [--hz 200] [--steps -36 -30 -24 -18 -12 -6 0]
"""
import argparse, wave, numpy as np
ap = argparse.ArgumentParser(); ap.add_argument("out"); ap.add_argument("--hz", type=float, default=200)
ap.add_argument("--steps", type=float, nargs="*", default=[-36, -30, -24, -18, -12, -6, 0])
ap.add_argument("--hold", type=float, default=10); ap.add_argument("--gap", type=float, default=1)
a = ap.parse_args(); sr = 44100
parts = [np.zeros(int(sr * 2))]
for db in a.steps:
    t = np.arange(int(sr * a.hold)) / sr
    env = np.minimum(1, np.minimum(t, a.hold - t) / 0.02)
    parts += [np.sin(2 * np.pi * a.hz * t) * env * 10 ** (db / 20), np.zeros(int(sr * a.gap))]
x = np.concatenate(parts); y = (np.clip(x, -1, 1) * 32767).astype(np.int16)
with wave.open(a.out, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes(np.column_stack([y, y]).tobytes())
print(a.out, f"{len(x)/sr:.0f} s; steps (dB):", a.steps, "hold", a.hold, "s each, starting after 2 s")
