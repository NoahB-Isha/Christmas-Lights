"""
audio.py -- music for the timeline: analysis cache, beat grids, sections.

One `Track` per audio file. Analysis (lightshow.music) is run once at 60 fps
and cached in out/studio/<stem>.npz; the effects index it by file time.

BEAT GRID
    The owner may type a BPM (and drag the first-beat offset); otherwise the
    detected beats are used. A typed BPM always wins -- the tracker locks to
    subdivisions on some songs (Carol of the Bells: 168 -> felt 84).

SECTIONS ("robust detection based on bpm and measures")
    Bars come from the beat grid. Per-bar timbre vectors -> novelty between the
    two bars before and the two bars after each bar line, blended with the
    energy step there. Peaks become section boundaries with a minimum of 4
    bars between them, and a boundary that is within one bar of a 4-bar
    phrase count from the previous boundary snaps onto the phrase. Everything
    lands ON a bar line, so clips snapped to sections are musically placed.
"""

import os
import numpy as np
from scipy.ndimage import uniform_filter1d, maximum_filter1d

from .. import music

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
CACHE = os.path.join(ROOT, "out", "studio")
AFPS = 60                          # analysis grid; independent of the show fps

KEEP = ("rms", "low", "mid", "high", "centroid", "harm", "perc", "hit", "hit_high",
        "beat_env", "downbeat_env", "chroma_f", "beats", "downbeats", "onsets_perc")
CACHE_VERSION = 2                  # bump when the cached feature set changes
N_BANDS = 8                        # EQ bands for the visualiser, log-spaced 40 Hz .. 8 kHz
BAND_EDGES = np.logspace(np.log10(40), np.log10(8000), N_BANDS + 1)



def ramp_beats(t0, t1, bpm0, bpm1, first):
    """Beat times of a linear tempo ramp: bpm0 at t0 rising (or falling) to bpm1 at t1,
    the first beat at `first` (>= t0). Beat count is the integral of the tempo, so the
    k-th beat solves a quadratic in (t - first)."""
    t0, t1, first = float(t0), float(t1), float(first)
    if t1 <= first:
        return np.array([])
    a = (bpm1 - bpm0) / (2.0 * (t1 - t0))             # bpm per second / 2
    # tempo at the first beat (the ramp runs from t0, not from the first beat)
    b0 = bpm0 + 2.0 * a * (first - t0)
    total = (b0 * (t1 - first) + a * (t1 - first) ** 2) / 60.0
    k = np.arange(0, int(total) + 1, dtype=float)
    if abs(a) < 1e-9:
        x = 60.0 * k / b0
    else:
        x = (-b0 + np.sqrt(np.maximum(0.0, b0 * b0 + 4.0 * a * 60.0 * k))) / (2.0 * a)
    b = first + x
    return b[(b >= t0) & (b < t1)]

class Track:
    def __init__(self, path):
        self.path = path if os.path.isabs(path) else os.path.join(ROOT, path)
        self.stem = os.path.splitext(os.path.basename(self.path))[0]
        self._load()

    def _load(self):
        os.makedirs(CACHE, exist_ok=True)
        cpath = os.path.join(CACHE, f"{self.stem}.v{CACHE_VERSION}.npz")
        if os.path.exists(cpath) and os.path.getmtime(cpath) >= os.path.getmtime(self.path):
            d = np.load(cpath)
            for k in d.files:
                setattr(self, k, d[k])
            self.n_frames = int(self.n_frames); self.duration = float(self.duration)
            self.bpm = float(self.bpm); self.beats_per_bar = int(self.beats_per_bar)
            return
        print(f"analysing {os.path.basename(self.path)} (once; ~1 min for a 15-minute track) ...", flush=True)
        A = music.analyse(self.path, fps=AFPS)
        keep = {k: np.asarray(getattr(A, k)) for k in KEEP}
        keep.update(n_frames=A.n_frames, duration=A.duration, bpm=A.bpm,
                    beats_per_bar=getattr(A, "beats_per_bar", 4))
        # waveform peaks for the UI, 25 px per second
        y = np.abs(A.y)
        per = A.sr // 25
        n = len(y) // per
        keep["wave"] = y[:n * per].reshape(n, per).max(1).astype(np.float32)
        keep["novelty_secs"] = np.array([[s["start"], s["end"], s["intensity"]] for s in A.sections], float)
        # EQ bands: log-spaced magnitude sums, each normalised 1..99 pct, smoothed ~50 ms, on the 60 fps grid
        ft = np.arange(A.n_frames) / AFPS
        bands = np.zeros((A.n_frames, N_BANDS), np.float32)
        for k in range(N_BANDS):
            msk = (A.freqs >= BAND_EDGES[k]) & (A.freqs < BAND_EDGES[k + 1])
            v = A.S[:, msk].sum(1) if msk.any() else np.zeros(A.S.shape[0])
            lo, hi = np.percentile(v, 1), np.percentile(v, 99)
            v = np.clip((v - lo) / max(1e-9, hi - lo), 0, 1)
            bands[:, k] = uniform_filter1d(np.interp(ft, A.times, v), 3)
        keep["bands"] = bands
        np.savez(cpath, **keep)
        for k, v in keep.items():
            setattr(self, k, v)
        self.n_frames = int(self.n_frames); self.duration = float(self.duration)
        self.bpm = float(self.bpm); self.beats_per_bar = int(self.beats_per_bar)

    # ---------------------------------------------------------- features
    def frame(self, ft):
        return int(min(self.n_frames - 1, max(0, round(ft * AFPS))))

    # --------------------------------------------------------- beat grid
    def grid(self, bpm=None, beat_offset=None, beats_per_bar=4):
        """-> (beats, bpm, beats_per_bar) in FILE seconds. Typed BPM wins."""
        bpb = int(beats_per_bar or 4)
        if bpm:
            bpm = float(bpm)
            off = float(beat_offset) if beat_offset is not None else self._best_offset(bpm)
            beats = np.arange(off, self.duration, 60.0 / bpm)
            return beats, bpm, bpb
        if beat_offset is not None and len(self.beats) > 1:
            beats = self.beats + (float(beat_offset) - self.beats[0])
            return beats[(beats >= 0) & (beats < self.duration)], self.bpm, bpb
        return np.asarray(self.beats), self.bpm, bpb

    def grid_songs(self, songs, default_bpm=None, default_offset=None, default_bpb=4):
        """Tempo map: songs = [{from, to, bpm, beats_per_bar, beat_offset}] in FILE
        seconds (a medley changes tempo between songs). -> (beats, song_index
        per beat, songs_used). With no songs the whole file is one song."""
        if not songs:
            beats, bpm, bpb = self.grid(default_bpm, default_offset, default_bpb)
            return beats, np.zeros(len(beats), int), [{"from": 0.0, "to": self.duration, "bpm": bpm, "beats_per_bar": bpb, "name": self.stem}]
        allb, idx, used = [], [], []
        for k, sg in enumerate(songs):
            t0, t1 = float(sg.get("from", 0.0)), float(sg.get("to", self.duration))
            bpm = sg.get("bpm")
            bpb = int(sg.get("beats_per_bar") or 4)
            bpm_end = sg.get("bpm_end")
            if bpm and bpm_end and abs(float(bpm_end) - float(bpm)) > 0.05:
                # accelerando / ritardando: the tempo ramps linearly from bpm at `from` to bpm_end at `to`
                off = sg.get("beat_offset")
                off = float(off) if off is not None else t0 + self._best_offset_ramp(float(bpm), float(bpm_end), t0, t1)
                b = ramp_beats(t0, t1, float(bpm), float(bpm_end), off)
            elif bpm:
                off = sg.get("beat_offset")
                off = float(off) if off is not None else t0 + self._best_offset(float(bpm), t0, t1)
                b = np.arange(off, t1, 60.0 / float(bpm))
                b = b[b >= t0]
            else:
                b = np.asarray(self.beats); b = b[(b >= t0) & (b < t1)]
                bpm = self.bpm
            allb.append(b); idx.append(np.full(len(b), k))
            used.append({**sg, "from": t0, "to": t1, "bpm": float(bpm), "beats_per_bar": bpb})
        beats = np.concatenate(allb) if allb else np.array([])
        return beats, (np.concatenate(idx) if idx else np.array([], int)), used

    def _best_offset_ramp(self, bpm0, bpm1, t0, t1):
        """Phase of a tempo ramp: the first-beat offset (0..one beat at the start tempo)
        whose ramped grid catches the most percussive-onset energy over the whole ramp."""
        period = 60.0 / bpm0
        best, bv = 0.0, -1.0
        for off in np.linspace(0, period, 24, endpoint=False):
            b = ramp_beats(t0, t1, bpm0, bpm1, t0 + off)
            idx = np.round(b * AFPS).astype(int); idx = idx[idx < self.n_frames]
            v = self.hit[idx].sum() if len(idx) else 0.0
            if v > bv:
                bv, best = v, off
        return float(round(best, 4))

    def _best_offset(self, bpm, t0=0.0, t1=None):
        """Phase of a typed BPM: the offset (0..one beat) whose grid catches
        the most percussive-onset energy."""
        period = 60.0 / bpm
        t1 = self.duration if t1 is None else t1
        env = self.hit
        best, bv = 0.0, -1.0
        for off in np.linspace(0, period, 24, endpoint=False):
            idx = np.round((np.arange(t0 + off, min(t1, t0 + 90.0), period)) * AFPS).astype(int)
            idx = idx[idx < self.n_frames]
            v = env[idx].sum()
            if v > bv:
                bv, best = v, off
        return float(round(best, 4))

    # ---------------------------------------------------------- sections
    def sections_songs(self, songs, **kw):
        """Sections per song of a tempo map; song boundaries are always cuts."""
        beats, idx, used = self.grid_songs(songs)
        out = []
        for k, sg in enumerate(used):
            b = beats[idx == k]
            secs = self.sections(b, sg["beats_per_bar"], t_lo=sg["from"], t_hi=sg["to"], **kw)
            out.extend((s0, s1, kind, k) for s0, s1, kind in secs)
        return out, used

    def sections(self, beats, bpb=4, min_bars=4, phrase=4, thresh=0.3, t_lo=0.0, t_hi=None):
        """-> [(t0, t1, kind)] in FILE seconds, all on bar lines."""
        t_hi = self.duration if t_hi is None else t_hi
        beats = np.asarray(beats)
        if len(beats) < bpb * 2 * min_bars:
            return [(t_lo, t_hi, "all")]
        bars = beats[::bpb]
        if bars[0] > t_lo + 0.05:
            bars = np.concatenate([[t_lo], bars])
        bars = np.append(bars, t_hi)
        # per-bar feature vector
        F = []
        for a, b in zip(bars[:-1], bars[1:]):
            i0, i1 = self.frame(a), max(self.frame(a) + 1, self.frame(b))
            v = [self.rms[i0:i1].mean(), self.low[i0:i1].mean(), self.mid[i0:i1].mean(),
                 self.high[i0:i1].mean(), self.centroid[i0:i1].mean(), self.perc[i0:i1].mean(),
                 self.hit[i0:i1].mean()]
            v += list(self.chroma_f[i0:i1].mean(0) * 0.6)
            F.append(v)
        F = np.array(F)
        F = (F - F.mean(0)) / (F.std(0) + 1e-9)
        nb = len(F)
        nov = np.zeros(nb)
        for k in range(1, nb):
            a = F[max(0, k - 2):k].mean(0); b = F[k:min(nb, k + 2)].mean(0)
            cos = 1 - (a @ b) / max(1e-9, np.linalg.norm(a) * np.linalg.norm(b))
            e_step = abs(F[k, 0] - F[k - 1, 0]) * 0.35
            nov[k] = cos + e_step
        nov = nov / max(1e-9, nov.max())
        peak = (nov >= maximum_filter1d(nov, min_bars)) & (nov > thresh)
        cand = [k for k in range(1, nb) if peak[k]]
        cuts = [0]
        for k in cand:
            if k - cuts[-1] < min_bars:
                continue
            # snap onto a phrase multiple from the previous cut when within one bar
            d = k - cuts[-1]
            r = d % phrase
            if r == 1 and d - 1 >= min_bars and k - 1 not in cuts:
                k = k - 1
            elif r == phrase - 1 and k + 1 < nb:
                k = k + 1
            if k - cuts[-1] >= min_bars and k < nb:
                cuts.append(k)
        cuts.append(nb)
        out = []
        for a, b in zip(cuts[:-1], cuts[1:]):
            e = float(F[a:b, 0].mean())
            kind = "loud" if e > 0.5 else ("quiet" if e < -0.5 else "mid")
            out.append((float(bars[a]), float(bars[b]), kind))
        return out

    # ---------------------------------------------------------------- ui
    def ui_json(self, songs=None, bpm=None, beat_offset=None, beats_per_bar=4):
        beats, idx, used = self.grid_songs(songs, bpm, beat_offset, beats_per_bar)
        # downbeats: every bpb-th beat counted from each song's first beat
        bars = []
        for k, sg in enumerate(used):
            b = beats[idx == k]
            bars.extend(b[::sg["beats_per_bar"]].tolist())
        return {"duration": self.duration, "bpm_detected": self.bpm, "beats_per_bar_detected": self.beats_per_bar,
                "songs": used,
                "beats": [round(float(b), 3) for b in beats], "bars": [round(float(b), 3) for b in bars],
                "wave": [round(float(v), 3) for v in self.wave], "wave_hz": 25}
