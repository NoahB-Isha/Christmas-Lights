#!/usr/bin/env python3
"""
song_report.py -- per-song analysis of a medley, using the song markers.

    python tools/song_report.py                 # markers.json + show16.mp3 -> out/songs.json

A medley has no single tempo. For each stretch between `song` markers this
re-runs the beat tracker on that stretch alone and reports tempo, meter hint,
energy and the sections the owner marked inside it. out/songs.json is what
the show renderer reads for per-song beat grids.
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from lightshow.music import decode, Analysis, SR   # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def mmss(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def main(markers_path, song, out):
    M = json.load(open(markers_path, encoding="utf-8"))
    y = decode(song)
    dur = len(y) / SR
    marks = sorted(M["markers"], key=lambda m: m["t"])
    songs = [m for m in marks if m["type"] == "song"]
    report = []
    for i, s in enumerate(songs):
        t0 = s["t"]
        t1 = songs[i + 1]["t"] if i + 1 < len(songs) else dur
        seg = y[int(t0 * SR):int(t1 * SR)]
        a = Analysis(seg)
        secs = [m for m in marks if m["type"] == "section" and t0 < m["t"] < t1]
        rms = float(np.sqrt((seg ** 2).mean()))
        report.append({
            "index": i + 1, "label": s["label"], "start": t0, "end": t1,
            "seconds": round(t1 - t0, 2), "bpm": round(float(a.bpm), 1),
            "beats_per_bar": int(a.beats_per_bar), "meter_contrast": round(float(a.meter_contrast), 3),
            "rms": round(rms, 4), "intensity": s.get("intensity"),
            "beats": [round(float(b) + t0, 3) for b in a.beats],
            "downbeats": [round(float(b) + t0, 3) for b in a.downbeats],
            "sections": [{"t": m["t"], "label": m["label"], "intensity": m.get("intensity"),
                          "palette": m.get("palette")} for m in secs],
        })
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"audio": M.get("audio"), "duration": dur, "songs": report}, open(out, "w"), indent=1)
    rmax = max(r["rms"] for r in report)
    print(f"{len(report)} songs in {mmss(dur)}\n")
    print(f"{'#':>2} {'start':>8} {'len':>6} {'bpm':>6} {'bar':>3} {'loud':>4} sections  label")
    for r in report:
        print(f"{r['index']:>2} {mmss(r['start']):>8} {r['seconds']:>6.1f} {r['bpm']:>6.1f} "
              f"{r['beats_per_bar']:>3} {r['rms']/rmax:>4.2f} {len(r['sections']):>8}  {r['label'][:60]}")
    print(f"\nwrote {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "assets", "show", "markers.json"),
         sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "assets", "audio", "show16.mp3"),
         os.path.join(ROOT, "out", "songs.json"))
