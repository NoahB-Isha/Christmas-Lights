#!/usr/bin/env python3
"""
make_cue_track.py -- build the stereo "music + cue beeps" file for the bench.

The bench runner is the laptop: a stereo file where one channel carries the
MUSIC (to the speakers) and the other carries CUE BEEPS (to the GC-102C audio
box, which detects low-frequency drum hits and emits a DMX scene-select).
Play the file with the laptop's output split L/R and both sides stay locked to
one clock -- no runner box needed until the yard.

    # show: music on LEFT, one start beep on RIGHT at t=0 (scene 1 = whole show)
    python tools/make_cue_track.py assets/audio/show16.mp3 out/cue_show.wav

    # split-show fallback: a beep at every cue time from a cues.json
    python tools/make_cue_track.py assets/audio/show16.mp3 out/cue_show.wav --cues out/cues.json

    # characterise the box: no music, a beep every 10 s for 3 minutes.
    # Watch the controller: does each beep ADVANCE one scene, restart the
    # current one, or pick at random? What is the shortest gap it honours?
    python tools/make_cue_track.py --test --every 10 --seconds 180 out/cue_test.wav

    # after the test, shift the music so the lights land on the beat
    python tools/make_cue_track.py assets/audio/show16.mp3 out/cue_show.wav --music-delay-ms 120

BEEP DESIGN
    The GC-102C is a drum-beat detector, so the cue is shaped like a kick: an
    80 Hz sine with a fast attack and ~150 ms exponential decay at full scale,
    with a click transient on top. Nothing musical leaks into that channel, so
    the detector only ever sees our cues. Tune --beep-hz / --beep-ms if the box
    ignores it; --gap-ms puts several beeps in a burst for boxes that count.

CHANNELS
    --cue-channel right (default) puts beeps on RIGHT, music on LEFT. A TRS
    splitter or a Y cable off the headphone jack gives you two mono feeds.
    Make sure the OS output is NOT set to mono and no "enhancement" is on.

OUTPUT
    16-bit 44.1 kHz stereo WAV. The music channel is peak-normalised to -1 dBFS
    unless --music-gain-db says otherwise. Also writes <out>.cues.json listing
    every beep time so the render can be checked against it.
"""

import argparse, json, math, os, shutil, subprocess, sys, wave

import numpy as np

SR = 44100


def decode(path, sr=SR):
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found (macOS: brew install ffmpeg)")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1",
                          "-ar", str(sr), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def beep(sr, hz=80.0, ms=150.0, click=True, multitone=False):
    """One cue. multitone=True: a broadband 'drum hit' -- several tones (hz,
    2.5x, 6x, 12x) plus a noise burst, all decaying together. The GC-102C's
    beat detector fired on a multitone generator but ignored single sine
    beeps, so this is the default for real cue tracks."""
    n = int(sr * ms / 1000)
    t = np.arange(n) / sr
    env = np.exp(-t / (ms / 1000 / 4.0))
    attack = np.minimum(1.0, t / 0.002)
    if multitone:
        rng = np.random.default_rng(7)
        y = np.zeros(n)
        for k, (mult, g) in enumerate(((1, 1.0), (2.5, 0.8), (6, 0.6), (12, 0.45))):
            y += g * np.sin(2 * math.pi * hz * mult * t + k)
        y += 0.5 * rng.standard_normal(n) * np.exp(-t / 0.02)   # noise burst on the attack
        y = y / np.abs(y).max() * env * attack
    else:
        y = np.sin(2 * math.pi * hz * t) * env * attack
    if click:                                   # broadband transient helps onset detectors
        k = int(sr * 0.004)
        y[:k] += np.linspace(1.0, 0.0, k) * np.sign(np.sin(np.arange(k) * 1.7))
    return np.clip(y, -1, 1)


def parse_time(s):
    if isinstance(s, (int, float)):
        return float(s)
    if ":" in s:
        m, sec = s.split(":")
        return int(m) * 60 + float(sec)
    return float(s)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("music", nargs="?", help="music file (omit with --test)")
    ap.add_argument("out", help="output .wav")
    ap.add_argument("--cues", help="cues.json: {\"cues\":[{\"t\":sec,...}]} or a list of times; default one cue at 0")
    ap.add_argument("--at", nargs="*", default=None, help="explicit cue times, e.g. 0 1:23.13 3:10.41")
    ap.add_argument("--test", action="store_true", help="no music; beeps every --every seconds")
    ap.add_argument("--every", type=float, default=10.0)
    ap.add_argument("--seconds", type=float, default=None, help="total length (default: music length + 2 s)")
    ap.add_argument("--cue-channel", choices=["left", "right"], default="right")
    ap.add_argument("--music-delay-ms", type=float, default=0.0,
                    help="delay MUSIC relative to the beep (positive = music later) to absorb box+controller start latency")
    ap.add_argument("--music-gain-db", type=float, default=-1.0, help="music peak level")
    ap.add_argument("--beep-hz", type=float, default=80.0)
    ap.add_argument("--beep-ms", type=float, default=150.0)
    ap.add_argument("--beep-gain-db", type=float, default=0.0)
    ap.add_argument("--sine", action="store_true", help="plain sine beep instead of the broadband multitone hit")
    ap.add_argument("--repeat", type=int, default=1, help="beeps per cue (burst)")
    ap.add_argument("--gap-ms", type=float, default=250.0, help="gap between beeps in a burst")
    ap.add_argument("--pre-roll", type=float, default=1.0, help="silence before t=0 so the first beep is not clipped by playback start")
    a = ap.parse_args()

    # ---- cue times
    if a.test:
        total = a.seconds or 180.0
        cues = list(np.arange(0.0, total, a.every))
        music = None
    else:
        if not a.music:
            ap.error("music file required unless --test")
        music = decode(a.music)
        total = a.seconds or (len(music) / SR + 2.0)
        if a.at:
            cues = [parse_time(x) for x in a.at]
        elif a.cues:
            d = json.load(open(a.cues))
            items = d["cues"] if isinstance(d, dict) else d
            cues = [parse_time(c["t"] if isinstance(c, dict) else c) for c in items]
        else:
            cues = [0.0]
    cues = sorted(set(round(c, 3) for c in cues))

    # ---- build channels
    n = int(SR * (a.pre_roll + total))
    cue_ch = np.zeros(n)
    b = beep(SR, a.beep_hz, a.beep_ms, multitone=not a.sine) * (10 ** (a.beep_gain_db / 20))
    for c in cues:
        for r in range(a.repeat):
            i = int(SR * (a.pre_roll + c + r * a.gap_ms / 1000))
            j = min(n, i + len(b))
            if i < n:
                cue_ch[i:j] += b[:j - i]
    cue_ch = np.clip(cue_ch, -1, 1)

    mus_ch = np.zeros(n)
    if music is not None:
        peak = np.abs(music).max() or 1.0
        music = music / peak * (10 ** (a.music_gain_db / 20))
        i = int(SR * (a.pre_roll + a.music_delay_ms / 1000))
        j = min(n, i + len(music))
        mus_ch[i:j] = music[:j - i]

    left, right = (mus_ch, cue_ch) if a.cue_channel == "right" else (cue_ch, mus_ch)
    stereo = np.column_stack([left, right])
    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with wave.open(a.out, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    meta = {"out": a.out, "sample_rate": SR, "seconds": round(n / SR, 3),
            "pre_roll_s": a.pre_roll, "music": a.music, "music_delay_ms": a.music_delay_ms,
            "cue_channel": a.cue_channel, "music_channel": "left" if a.cue_channel == "right" else "right",
            "beep": {"hz": a.beep_hz, "ms": a.beep_ms, "repeat": a.repeat, "gap_ms": a.gap_ms},
            "cues_s": cues, "cues_in_file_s": [round(c + a.pre_roll, 3) for c in cues]}
    with open(a.out + ".cues.json", "w") as fh:
        json.dump(meta, fh, indent=1)
    print(f"{a.out}: {n/SR:.1f} s stereo  music={meta['music_channel']}  cues={a.cue_channel} "
          f"({len(cues)} beeps: {', '.join(f'{c:.2f}' for c in cues[:8])}{' ...' if len(cues) > 8 else ''})")
    if music is not None:
        print(f"music delayed {a.music_delay_ms:.0f} ms after the beep; pre-roll {a.pre_roll:.1f} s")


if __name__ == "__main__":
    main()
