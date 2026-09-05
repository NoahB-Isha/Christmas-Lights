#!/usr/bin/env python3
"""
dmx_diff.py -- find the meaningful channels in a captured DMX stream.

    python tools/dmx_diff.py capture.csv [--events 12.4,31.9,55.0]
    python tools/dmx_diff.py capture.csv --demo        # synthetic self-test

WHY

A DMX universe is 512 channels and an audio-interpretation box probably uses
three or four of them. Staring at a 512-column capture is hopeless; what you
want is "which channels actually do anything, and which ones changed at the
moment the scene changed".

INPUT

CSV, one row per DMX frame. Either:
    time,ch1,ch2,...            (first column parsed as seconds if it looks
    ch1,ch2,...                  like a float and the rest are 0-255)
Rows may be short; missing channels are treated as 0. This matches what
sigrok/PulseView, an Enttec dump, or a hand-rolled logger will give you.

WHAT IT REPORTS

  1. Channel activity      -- constant, binary, stepped, or continuous.
     A scene selector is nearly always STEPPED: a handful of discrete values
     held for long stretches.
  2. Change points         -- when each active channel changed value.
  3. Correlation to events -- if you pass --events with the times you saw
     the scene change, channels whose transitions line up are ranked first.
     That is the answer you are looking for.

WHAT TO DO WITH IT

Once you know the scene channel and its values, you can drive the unit from
any DMX source. Replaying "scene N" is then also a START TRIGGER, which is
the thing that would remove hand-timing from the whole show.

If nothing correlates, the box may not be sending standard DMX, or the unit
may respond to something other than level changes.
"""

import argparse, csv, math, os, sys
import numpy as np


def load(path):
    rows, times = [], []
    with open(path, newline="") as fh:
        for rec in csv.reader(fh):
            if not rec:
                continue
            first = rec[0].strip()
            if first.lower() in ("time", "t", "timestamp"):      # header row
                continue
            vals = rec
            t = None
            try:
                f = float(first)
                # treat col 0 as a timestamp if it is fractional or > 255
                if ("." in first) or f > 255:
                    t = f
                    vals = rec[1:]
            except ValueError:
                continue
            try:
                v = [int(float(x)) for x in vals if x.strip() != ""]
            except ValueError:
                continue
            rows.append(v)
            times.append(t)
    if not rows:
        raise SystemExit(f"no usable rows in {path}")
    width = max(len(r) for r in rows)
    arr = np.zeros((len(rows), width), np.int16)
    for i, r in enumerate(rows):
        arr[i, :len(r)] = r
    if times[0] is None:
        times = np.arange(len(rows)) / 44.0        # DMX is ~44 fps
    else:
        times = np.array([t if t is not None else np.nan for t in times], float)
    return arr, np.asarray(times, float)


def classify(col):
    u = np.unique(col)
    if len(u) == 1:
        return "constant", u
    if len(u) == 2:
        return "binary", u
    if len(u) <= 12:
        return "stepped", u                       # <-- scene selectors live here
    return "continuous", u


def changes(col, times, min_hold=0.15):
    """Times at which the value changed and then held for min_hold."""
    idx = np.flatnonzero(np.diff(col) != 0) + 1
    out = []
    for i in idx:
        j = i
        while j + 1 < len(col) and col[j + 1] == col[i]:
            j += 1
        if times[j] - times[i] >= min_hold or j == len(col) - 1:
            out.append((float(times[i]), int(col[i - 1]), int(col[i])))
    return out


def score_against(events, ch_changes, tol=0.5):
    """Fraction of events matched by a change within tol seconds."""
    if not events or not ch_changes:
        return 0.0
    ts = np.array([c[0] for c in ch_changes])
    hit = sum(1 for e in events if np.min(np.abs(ts - e)) <= tol)
    return hit / len(events)


def demo(path):
    """Synthetic capture: ch12 = scene select, ch40 = brightness ramp,
    ch77 = a strobe flag, everything else idle. Used to self-test."""
    fps, dur = 44, 60.0
    n = int(fps * dur)
    a = np.zeros((n, 96), np.int16)
    scene_at = [0.0, 12.4, 31.9, 44.2, 55.0]
    vals = [10, 40, 70, 100, 130]
    for i in range(n):
        t = i / fps
        s = max(k for k, st in enumerate(scene_at) if t >= st)
        a[i, 11] = vals[s]
        a[i, 39] = int(127 + 120 * math.sin(t * 0.7))
        a[i, 76] = 255 if (t % 4) < 0.4 else 0
        a[i, 5] = 255
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        for i in range(n):
            w.writerow([round(i / fps, 4)] + list(a[i]))
    return scene_at[1:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("--events", default="",
                    help="comma-separated seconds when you SAW a scene change")
    ap.add_argument("--demo", action="store_true",
                    help="write a synthetic capture first and analyse it")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    events = [float(x) for x in args.events.split(",") if x.strip()]
    if args.demo:
        events = demo(args.capture)
        print(f"wrote synthetic capture to {args.capture}")
        print(f"ground truth: scene channel is 12, changes at {events}\n")

    a, times = load(args.capture)
    print(f"{a.shape[0]} frames, {a.shape[1]} channels, "
          f"{times[-1]-times[0]:.1f}s, ~{a.shape[0]/max(1e-9,times[-1]-times[0]):.0f} fps\n")

    rows = []
    for c in range(a.shape[1]):
        kind, u = classify(a[:, c])
        if kind == "constant":
            continue
        ch = changes(a[:, c], times)
        rows.append({"ch": c + 1, "kind": kind, "vals": u, "changes": ch,
                     "score": score_against(events, ch)})

    if not rows:
        print("every channel is constant -- nothing is being modulated.")
        const = [c + 1 for c in range(a.shape[1]) if len(np.unique(a[:, c])) == 1
                 and a[0, c] != 0]
        if const:
            print(f"non-zero constants on channels {const} "
                  f"(values {[int(a[0,c-1]) for c in const]})")
        return

    order = ["stepped", "binary", "continuous"]
    rows.sort(key=lambda r: (-r["score"], order.index(r["kind"]), len(r["changes"])))

    if events:
        print(f"scored against {len(events)} observed scene changes: "
              f"{', '.join(f'{e:.1f}s' for e in events)}\n")
    print(f"{'ch':>4} {'kind':>11} {'distinct':>9} {'changes':>8} "
          f"{'match':>6}  values")
    for r in rows[:args.top]:
        vs = ",".join(str(int(v)) for v in r["vals"][:8])
        if len(r["vals"]) > 8:
            vs += ",..."
        m = f"{r['score']*100:.0f}%" if events else "-"
        print(f"{r['ch']:>4} {r['kind']:>11} {len(r['vals']):>9} "
              f"{len(r['changes']):>8} {m:>6}  {vs}")

    best = rows[0]
    print()
    if events and best["score"] >= 0.8:
        print(f"==> channel {best['ch']} tracks the scene changes "
              f"({best['score']*100:.0f}% matched).")
        print("    Values in order of appearance:")
        seen, seq = set(), []
        for t, old, new in best["changes"]:
            if new not in seen:
                seen.add(new); seq.append((t, new))
        for t, v in seq:
            print(f"      t={t:7.2f}s  value {v}")
        print("\n    Send these values on that channel from any DMX source to "
              "select scenes.\n    A scene select is also a START TRIGGER.")
    elif events:
        print("No channel matched the events well. Either the box is not "
              "sending\nstandard DMX, or scene changes are signalled some "
              "other way (a value\nPULSE rather than a level, or a different "
              "universe).")
    else:
        print("Re-run with --events listing the times you saw the scene "
              "change,\nand the matching channel will be ranked first.")
        print("Stepped channels with few distinct values are the usual "
              "suspects.")


if __name__ == "__main__":
    main()
