#!/usr/bin/env python3
"""
music.py -- audio analysis for driving a light show. numpy + scipy + ffmpeg.

No librosa. ffmpeg handles decoding (any format), and everything else is a
few hundred lines of numpy. That keeps the install trivial on a Mac and
means the analysis is fully inspectable -- which matters, because when a
cue lands in the wrong place you need to see why.

WHAT IT EXTRACTS, and what each is good for

  slow ────────────────────────────────────────────────────► fast
  sections      tempo/beats     band energy      onsets
  (10-60 s)     (0.5 s grid)    (continuous)     (instant)

  sections   novelty over a self-similarity matrix of timbre features.
             -> which LOOK is active. Drives palette and layer mix.
  tempo      autocorrelation of the onset envelope.
  beats      comb-filter phase lock to the tempo, then downbeats every 4.
             -> quantise anything discrete: arm rotation, strobe hits.
  bands      low / mid / high energy envelopes, perceptually spaced.
             -> continuous modulation. Bass to radius, highs to sparkle.
  onsets     spectral flux with an adaptive threshold, split into
             percussive and full-band.
             -> instant events. One onset = one flash.
  centroid   spectral centroid in Hz -> "brightness" of the timbre.
             -> hue / colour temperature.
  chroma     12 pitch classes -> harmonic colour that follows the key.
  hpss       harmonic vs percussive, by median filtering the spectrogram.
             -> lets sustained pads and drum hits drive separate layers,
                which is what makes layering read as musical rather than
                as one envelope applied to everything.

Everything is resampled onto a uniform frame grid at the show's frame rate,
so a renderer can just index by frame.
"""

import subprocess, shutil, math
import numpy as np
from scipy.ndimage import median_filter, maximum_filter1d, uniform_filter1d

SR = 22050
HOP = 256                      # 11.6 ms at 22050 -> finer than one 60fps frame
NFFT = 1024


# ------------------------------------------------------------------ decode
def decode(path, sr=SR):
    """Any audio file -> mono float32 in [-1, 1], via ffmpeg."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found. macOS: brew install ffmpeg")
    cmd = ["ffmpeg", "-v", "error", "-i", str(path),
           "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def synth_demo(seconds=72, sr=SR, bpm=120):
    """A synthetic track with deliberately clear structure, for validating
    the analysis without needing a real file. Sections: intro pad, verse
    (kick+bass), chorus (full+hats), bridge (melody), outro."""
    n = int(seconds * sr)
    t = np.arange(n) / sr
    out = np.zeros(n, np.float32)
    spb = 60.0 / bpm

    def add(sig, at):
        i = int(at * sr)
        j = min(n, i + len(sig))
        if i < n:
            out[i:j] += sig[:j - i]

    def kick(dur=0.16):
        x = np.arange(int(dur * sr)) / sr
        f = 110 * np.exp(-x * 28) + 45
        return (np.sin(2 * np.pi * f * x) * np.exp(-x * 16) * 0.9).astype(np.float32)

    def hat(dur=0.045):
        x = np.arange(int(dur * sr)) / sr
        return (np.random.default_rng(int(x[0] * 1e6) + len(x)).standard_normal(len(x))
                * np.exp(-x * 130) * 0.16).astype(np.float32)

    def snare(dur=0.13):
        x = np.arange(int(dur * sr)) / sr
        rng = np.random.default_rng(7)
        return ((rng.standard_normal(len(x)) * 0.5 + np.sin(2 * np.pi * 190 * x))
                * np.exp(-x * 24) * 0.45).astype(np.float32)

    def tone(freq, dur, amp=0.2, harm=3):
        x = np.arange(int(dur * sr)) / sr
        s = sum(np.sin(2 * np.pi * freq * k * x) / k for k in range(1, harm + 1))
        env = np.minimum(1, x * 12) * np.exp(-x * 1.2)
        return (s * env * amp).astype(np.float32)

    SEC = [(0, 12, "intro"), (12, 32, "verse"), (32, 52, "chorus"),
           (52, 62, "bridge"), (62, seconds, "outro")]
    scale = [220, 247, 262, 294, 330, 349, 392]
    for a, b, kind in SEC:
        beats = np.arange(a, b, spb)
        if kind in ("intro", "outro"):
            for k, f in enumerate([110, 165, 220]):
                add(tone(f, b - a, 0.13, 2), a)
        if kind in ("verse", "chorus"):
            for i, bt in enumerate(beats):
                add(kick(), bt)
                if i % 4 == 2:
                    add(snare(), bt)
                add(tone(scale[i % 7] / 2, spb * 0.9, 0.16, 4), bt)
        if kind == "chorus":
            for i, bt in enumerate(beats):
                for s in (0.0, 0.5):
                    add(hat(), bt + s * spb)
                add(tone(scale[(i * 3) % 7], spb * 0.5, 0.17, 5), bt)
                add(tone(scale[(i * 3 + 2) % 7], spb * 0.5, 0.12, 5), bt)
        if kind == "bridge":
            for i, bt in enumerate(beats):
                add(tone(scale[(i * 5) % 7], spb * 1.6, 0.22, 6), bt)
                if i % 2 == 0:
                    add(kick(0.12), bt)
    out /= max(1e-6, np.abs(out).max()) * 1.05
    return out


# --------------------------------------------------------------- spectrogram
def _stft(y, nfft=NFFT, hop=HOP):
    win = np.hanning(nfft).astype(np.float32)
    pad = nfft // 2
    yp = np.pad(y, pad, mode="reflect")
    nf = 1 + (len(yp) - nfft) // hop
    idx = np.arange(nfft)[None, :] + hop * np.arange(nf)[:, None]
    frames = yp[idx] * win
    return np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32)


def _norm(x, lo=1, hi=99):
    a, b = np.percentile(x, lo), np.percentile(x, hi)
    if b - a < 1e-9:
        return np.zeros_like(x)
    return np.clip((x - a) / (b - a), 0, 1)


class Analysis:
    """Every feature is exposed on a uniform per-frame grid at `fps`."""

    def __init__(self, y, sr=SR, fps=60, beats_per_bar=None):
        self.y, self.sr, self.fps = y, sr, fps
        self._force_bpb = beats_per_bar
        self.duration = len(y) / sr
        self.n_frames = int(math.ceil(self.duration * fps))

        S = _stft(y)
        self.S = S
        self.freqs = np.fft.rfftfreq(NFFT, 1 / sr)
        self.times = np.arange(S.shape[0]) * HOP / sr

        # --- harmonic / percussive split by median filtering ---
        H = median_filter(S, size=(17, 1))      # smooth in time -> sustained
        P = median_filter(S, size=(1, 17))      # smooth in freq -> transient
        mask = (P ** 2) / np.maximum(1e-9, P ** 2 + H ** 2)
        self.S_perc = S * mask
        self.S_harm = S * (1 - mask)

        # --- band energies (perceptually spaced) ---
        def band(spec, lo, hi):
            m = (self.freqs >= lo) & (self.freqs < hi)
            return spec[:, m].sum(1)
        self.raw_low = band(S, 20, 180)
        self.raw_mid = band(S, 180, 1800)
        self.raw_high = band(S, 1800, 8000)
        self.raw_rms = np.sqrt((S ** 2).mean(1))

        # --- spectral flux -> onset envelope ---
        d = np.diff(S, axis=0, prepend=S[:1])
        self.flux = np.maximum(0, d).sum(1)
        dp = np.diff(self.S_perc, axis=0, prepend=self.S_perc[:1])
        self.flux_perc = np.maximum(0, dp).sum(1)

        # --- spectral centroid ---
        tot = np.maximum(1e-9, S.sum(1))
        self.raw_centroid = (S * self.freqs[None, :]).sum(1) / tot

        # --- chroma (12 pitch classes) ---
        f = np.maximum(1e-6, self.freqs)
        midi = 69 + 12 * np.log2(f / 440.0)
        pc = np.mod(np.round(midi).astype(int), 12)
        keep = (f > 60) & (f < 5000)
        ch = np.zeros((S.shape[0], 12), np.float32)
        for k in range(12):
            m = keep & (pc == k)
            if m.any():
                ch[:, k] = S[:, m].sum(1)
        self.chroma = ch / np.maximum(1e-9, ch.sum(1, keepdims=True))

        self._tempo_and_beats()
        self._sections()
        self._onsets()
        self._resample()

    # ------------------------------------------------------------- tempo
    def _tempo_and_beats(self):
        env = uniform_filter1d(_norm(self.flux_perc), 3)
        env = env - env.mean()
        fps_env = self.sr / HOP
        ac = np.correlate(env, env, "full")[len(env) - 1:]
        lo, hi = int(fps_env * 60 / 200), int(fps_env * 60 / 60)   # 60..200 BPM
        hi = min(hi, len(ac) - 1)
        if hi <= lo:
            self.bpm, self.beats, self.downbeats = 120.0, np.array([]), np.array([])
            return
        lag = lo + int(np.argmax(ac[lo:hi]))
        self.bpm = float(60 * fps_env / lag)

        # phase: try every offset, keep the one with most envelope energy
        best, bestv = 0, -1e18
        for off in range(lag):
            idx = np.arange(off, len(env), lag)
            v = env[idx].sum()
            if v > bestv:
                bestv, best = v, off
        b = np.arange(best, len(env), lag) * HOP / self.sr
        self.beats = b[b < self.duration]
        # ---- meter: don't assume 4/4 ----
        # The beat tracker often locks to a fast subdivision (Carol of the
        # Bells came out at 166.7 BPM, i.e. the ostinato, not the pulse), so
        # the bar may span 2, 3, 4, 6 or 8 detected beats. Score each
        # grouping by how much low-band and percussive energy lands on its
        # best phase, and take the winner.
        low = _norm(self.raw_low)
        flux = _norm(self.flux_perc)

        def at(t):
            i = min(len(low) - 1, int(t * self.sr / HOP))
            return low[i] + flux[i]

        if len(self.beats) >= 8:
            sc = np.array([at(t) for t in self.beats])
            base = max(1e-9, sc.mean())
            # Score by CONTRAST against the average beat, not raw mean:
            # a real bar line should stand out. Candidates are 2/3/4/6 only --
            # 8 is not a meter, it is two bars of 4, and including it lets the
            # small-sample bias (fewer beats sampled -> luckier subset) win.
            best = (None, -1e18)
            for g in (2, 3, 4, 6):
                for ph in range(g):
                    v = float(sc[ph::g].mean() / base)
                    if v > best[1]:
                        best = ((g, ph), v)
            (self.beats_per_bar, phase) = best[0]
            self.meter_contrast = best[1]
            if self._force_bpb:
                self.beats_per_bar = self._force_bpb
                phase = max(range(self.beats_per_bar),
                            key=lambda p: sc[p::self.beats_per_bar].mean())
            self.downbeats = self.beats[phase::self.beats_per_bar]
        else:
            self.beats_per_bar = 4
            self.meter_contrast = 0.0
            self.downbeats = self.beats[:1]
        self.bar_seconds = self.beats_per_bar * 60.0 / self.bpm

    # ---------------------------------------------------------- sections
    def _sections(self, min_len=6.0):
        # timbre feature: coarse log-mel-ish bands + chroma, smoothed
        edges = np.logspace(np.log10(40), np.log10(9000), 17)
        F = []
        for i in range(len(edges) - 1):
            m = (self.freqs >= edges[i]) & (self.freqs < edges[i + 1])
            F.append(self.S[:, m].sum(1) if m.any() else np.zeros(self.S.shape[0]))
        F = np.log1p(np.array(F)).T
        F = np.hstack([F, self.chroma * F.sum(1, keepdims=True) * 0.35])
        step = max(1, int(0.25 * self.sr / HOP))          # 4 Hz feature rate
        F = uniform_filter1d(F, step, axis=0)[::step]
        F = (F - F.mean(0)) / (F.std(0) + 1e-9)

        # novelty: cosine distance across a small time lag
        L = max(2, int(2.0 * 4))                          # 2 s half-window
        nov = np.zeros(len(F))
        for i in range(L, len(F) - L):
            a = F[i - L:i].mean(0); b = F[i:i + L].mean(0)
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            nov[i] = 1 - (a @ b) / max(1e-9, na * nb)
        nov = _norm(uniform_filter1d(nov, 3))

        peak = (nov >= maximum_filter1d(nov, int(min_len * 4))) & (nov > 0.35)
        cuts = [0.0] + [i / 4.0 for i in np.flatnonzero(peak)] + [self.duration]
        cuts = sorted(set(round(c, 2) for c in cuts))
        merged = [cuts[0]]
        for c in cuts[1:]:
            if c - merged[-1] >= min_len:
                merged.append(c)
        if merged[-1] < self.duration:
            merged[-1] = self.duration
        self.novelty = nov

        # label each section by loudness+brightness rank, so a renderer can
        # pick a look without knowing anything about song form
        secs = []
        for a, b in zip(merged[:-1], merged[1:]):
            i0, i1 = int(a * self.sr / HOP), int(b * self.sr / HOP)
            i1 = max(i1, i0 + 1)
            secs.append({"start": a, "end": b,
                         "energy": float(_norm(self.raw_rms)[i0:i1].mean()),
                         "bright": float(_norm(self.raw_centroid)[i0:i1].mean()),
                         "perc": float(_norm(self.flux_perc)[i0:i1].mean())})
        if secs:
            order = np.argsort([s["energy"] for s in secs])
            for rank, i in enumerate(order):
                secs[i]["rank"] = rank / max(1, len(secs) - 1)
            # rank alone is ordinal: a near-silent intro can rank as high as
            # a real verse just by being 2nd quietest. Blend it with absolute
            # energy so quiet sections actually read as quiet.
            e = np.array([s["energy"] for s in secs])
            span = max(1e-9, e.max() - e.min())
            for i, s_ in enumerate(secs):
                s_["loud"] = float((e[i] - e.min()) / span)
                s_["intensity"] = float(0.5 * s_["rank"] + 0.5 * s_["loud"])
        self.sections = secs

    # ------------------------------------------------------------ onsets
    def _onsets(self):
        def pick(flux, delta=0.14, wait=0.05):
            e = _norm(flux)
            thr = uniform_filter1d(e, int(0.35 * self.sr / HOP)) + delta
            cand = (e > thr) & (e >= maximum_filter1d(e, 3))
            times, last = [], -1e9
            for i in np.flatnonzero(cand):
                t = i * HOP / self.sr
                if t - last >= wait:
                    times.append(t); last = t
            return np.array(times)
        self.onsets = pick(self.flux)
        self.onsets_perc = pick(self.flux_perc, 0.12, 0.045)
        hi = self.S[:, self.freqs > 3500].sum(1)
        self.onsets_high = pick(hi, 0.16, 0.04)

    # --------------------------------------------------------- frame grid
    def _resample(self):
        ft = np.arange(self.n_frames) / self.fps

        def rs(x, smooth=0):
            v = np.interp(ft, self.times, _norm(x))
            return uniform_filter1d(v, smooth) if smooth else v

        self.low = rs(self.raw_low, 3)
        self.mid = rs(self.raw_mid, 3)
        self.high = rs(self.raw_high, 2)
        self.rms = rs(self.raw_rms, 5)
        self.centroid = rs(self.raw_centroid, 5)
        self.harm = rs(np.sqrt((self.S_harm ** 2).mean(1)), 6)
        self.perc = rs(np.sqrt((self.S_perc ** 2).mean(1)), 1)
        self.chroma_f = np.stack([np.interp(ft, self.times, self.chroma[:, k])
                                  for k in range(12)], 1)

        def impulses(times, decay=0.16):
            v = np.zeros(self.n_frames)
            for t in times:
                i = int(round(t * self.fps))
                if 0 <= i < self.n_frames:
                    v[i] = 1.0
            k = math.exp(-1.0 / (decay * self.fps))
            for i in range(1, self.n_frames):
                v[i] = max(v[i], v[i - 1] * k)
            return v
        self.hit = impulses(self.onsets_perc, 0.14)
        self.hit_high = impulses(self.onsets_high, 0.08)
        self.beat_env = impulses(self.beats, 0.22)
        self.downbeat_env = impulses(self.downbeats, 0.40)

    # ---------------------------------------------------------- utilities
    def section_at(self, t):
        for s in self.sections:
            if s["start"] <= t < s["end"]:
                return s
        return self.sections[-1] if self.sections else None

    def beat_phase(self, t):
        """0..1 position within the current beat -- for smooth beat-locked
        motion rather than discrete flashes."""
        if len(self.beats) < 2:
            return (t * self.bpm / 60) % 1.0
        i = np.searchsorted(self.beats, t) - 1
        i = np.clip(i, 0, len(self.beats) - 2)
        a, b = self.beats[i], self.beats[i + 1]
        return float((t - a) / max(1e-6, b - a))

    def summary(self):
        L = [f"duration {self.duration:.1f}s  {self.n_frames} frames @ {self.fps}fps",
             f"tempo {self.bpm:.1f} BPM  {len(self.beats)} beats  "
             f"bar = {getattr(self,'beats_per_bar',4)} beats "
             f"({getattr(self,'bar_seconds',0):.2f}s)  "
             f"{len(self.downbeats)} downbeats "
             f"(contrast {getattr(self,'meter_contrast',0):.3f})",
             f"onsets: {len(self.onsets)} full, {len(self.onsets_perc)} percussive, "
             f"{len(self.onsets_high)} high-band",
             f"{len(self.sections)} sections:"]
        for i, s in enumerate(self.sections):
            L.append(f"   {i+1}. {s['start']:6.1f}-{s['end']:6.1f}s  "
                     f"({s['end']-s['start']:5.1f}s)  energy {s['energy']:.2f}  "
                     f"bright {s['bright']:.2f}  perc {s['perc']:.2f}  "
                     f"rank {s.get('rank',0):.2f}  "
                     f"intensity {s.get('intensity',0):.2f}")
        return "\n".join(L)


def analyse(path=None, fps=60, beats_per_bar=None, **kw):
    y = synth_demo(**kw) if path is None else decode(path)
    return Analysis(y, fps=fps, beats_per_bar=beats_per_bar)


if __name__ == "__main__":
    import sys
    a = analyse(sys.argv[1] if len(sys.argv) > 1 else None)
    print(a.summary())
