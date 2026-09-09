#!/usr/bin/env python3
"""
bench_play.py -- play the bench cue file to TWO audio devices at once:
music (left channel of cue_show) -> the laptop speakers, cue beep (right
channel) -> a second output (USB audio dongle) wired to the GC-102C box.

Why two devices: a Mac cannot drive its built-in speakers and its headphone
jack at the same time (the jack takes over the same device), so the box
needs its own output. Any $10 USB-C -> 3.5 mm adapter works. No aggregate
device, no BlackHole: the two streams start within a few ms of each other,
and after the beep the controller runs on its own clock anyway, so drift
between the two outputs does not matter.

    pip3 install sounddevice soundfile numpy
    python3 tools/bench_play.py --list
    python3 tools/bench_play.py cue_show.mp3 --music "MacBook Pro Speakers" --cue "USB"

Device names are matched case-insensitively as substrings. --offset-ms
shifts the MUSIC relative to the beep (+ = music later) without re-rendering.
An .mp3 is converted with afconvert (macOS) or ffmpeg if present.
"""

import argparse, os, subprocess, sys, tempfile, threading, time

import numpy as np


def to_wav(path):
    if path.lower().endswith(".wav"):
        return path
    out = os.path.join(tempfile.gettempdir(), os.path.splitext(os.path.basename(path))[0] + ".wav")
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(path):
        return out
    if subprocess.call(["which", "afconvert"], stdout=subprocess.DEVNULL) == 0:
        subprocess.check_call(["afconvert", "-f", "WAVE", "-d", "LEI16", path, out])
    else:
        subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-i", path, out])
    return out


def find_device(sd, needle, kind="output"):
    devs = sd.query_devices()
    for i, d in enumerate(devs):
        if needle.lower() in d["name"].lower() and d["max_output_channels"] > 0:
            return i, d
    sys.exit(f"no output device matching {needle!r}; try --list")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="cue_show.mp3 / .wav (music L, cue R)")
    ap.add_argument("--music", default="speakers", help="device for the music (substring)")
    ap.add_argument("--cue", default="usb", help="device for the beep -> GC-102C (substring)")
    ap.add_argument("--offset-ms", type=float, default=0.0, help="shift music vs beep (+ = music later)")
    ap.add_argument("--start", type=float, default=0.0, help="start at this second (for testing; beep is at 0)")
    ap.add_argument("--music-gain", type=float, default=1.0)
    ap.add_argument("--cue-gain", type=float, default=1.0)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    import sounddevice as sd, soundfile as sf
    if a.list or not a.file:
        print(sd.query_devices()); return

    data, sr = sf.read(to_wav(a.file), dtype="float32", always_2d=True)
    music, cue = data[:, 0], data[:, min(1, data.shape[1] - 1)]
    if a.offset_ms > 0:
        music = np.concatenate([np.zeros(int(sr * a.offset_ms / 1000), np.float32), music])
    elif a.offset_ms < 0:
        cue = np.concatenate([np.zeros(int(sr * -a.offset_ms / 1000), np.float32), cue])
    n = max(len(music), len(cue))
    music = np.pad(music, (0, n - len(music))) * a.music_gain
    cue = np.pad(cue, (0, n - len(cue))) * a.cue_gain
    s0 = int(a.start * sr)

    mi, md = find_device(sd, a.music); ci, cd = find_device(sd, a.cue)
    print(f"music -> [{mi}] {md['name']}\ncue   -> [{ci}] {cd['name']}\n{len(music)/sr:.1f} s, offset {a.offset_ms:+.0f} ms")

    def stream(dev, mono, chans):
        pos = {"i": s0}
        def cb(out, frames, t, status):
            i = pos["i"]; chunk = mono[i:i + frames]
            out.fill(0); out[:len(chunk), :] = chunk[:, None]
            pos["i"] = i + frames
            if i >= len(mono):
                raise sd.CallbackStop
        return sd.OutputStream(device=dev, channels=chans, samplerate=sr, callback=cb, blocksize=1024, latency="low")

    sm = stream(mi, music, min(2, md["max_output_channels"]))
    sc = stream(ci, cue, min(2, cd["max_output_channels"]))
    with sc, sm:                                  # start the cue stream first: its beep is what everything hangs on
        sc.start(); sm.start()
        t0 = time.time()
        try:
            while sm.active or sc.active:
                el = time.time() - t0 + a.start
                print(f"\r  {int(el // 60)}:{el % 60:05.2f}", end="", flush=True); time.sleep(0.25)
        except KeyboardInterrupt:
            pass
    print("\ndone")


if __name__ == "__main__":
    main()
