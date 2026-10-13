"""
engine.py -- turns the project timeline into frames.

    R = Renderer(project, layout, fps=30.3)
    frame = R.frame(T)              # {prop_id: (n,3) perceptual 0..1} for every prop
    R.reset()                       # after a seek: forget lamp/clip state

EFFECT CONTRACT (fx/*.py register with @effect)

    kind "anim"   fn(g, m, t, p, pal, st) -> {prop_id: (n,3)}
    kind "trans"  fn(g, m, u, p, pal, A, B, st) -> {prop_id: (n,3)}   u = progress 0..1
    kind "mod"    fn(g, m, t, p, pal, F, st) -> {prop_id: (n,3)}      F = what is playing

    g    GroupCtx -- the props of the group and their geometry (inches, world)
    m    Music    -- the music at this instant (levels, beat/bar phase, hits)
    t    seconds since the clip started
    p    dict of slider values (defaults filled in)
    pal  Palette
    st   dict, private to this clip instance; cleared on reset()

Everything an effect sizes is in INCHES (g.props[i].lx/ly/wx/wz, pitch) and
everything it times is in SECONDS. Return perceptual 0..1; composite layers
with lighten() (per-channel max), never addition. Effects that declare
lamp="incandescent"/"twinkle" get the LampBank applied after them.
"""

import math
import numpy as np
from scipy.ndimage import uniform_filter1d

from ..show import PropGeom
from ..lamps import LampBank
from ..effects import lighten
from . import palettes as PAL
from .audio import Track, AFPS


# ------------------------------------------------------------------ registry
class Slider:
    def __init__(self, name, label, default, lo=0.0, hi=1.0, step=0.01, kind="float", choices=None, unit=""):
        self.name, self.label, self.default = name, label, default
        self.lo, self.hi, self.step, self.kind, self.choices, self.unit = lo, hi, step, kind, choices, unit

    def json(self):
        return {"name": self.name, "label": self.label, "default": self.default, "lo": self.lo, "hi": self.hi,
                "step": self.step, "kind": self.kind, "choices": self.choices, "unit": self.unit}


def choice(name, label, default, choices):
    return Slider(name, label, default, kind="choice", choices=choices)


def toggle(name, label, default):
    return Slider(name, label, default, kind="bool")


def prop_pick(name, label, default=""):
    """A parameter whose value is one of the GROUP'S prop ids ("" = none). The
    inspector shows the group's props by name; effects resolve it with
    GroupCtx.index_of(). Feature-prop effects use it for "specific prop"."""
    return Slider(name, label, default, kind="prop")


# tags for the effect browser's filters: music (reacts to the track), slow (ambient / verse),
# regions (uses paint), incandescent (lamp model), geometry (uses the group's real distances)
DEFAULT_TAGS = {
    "starfield": ["slow"], "lavalamp": ["slow"], "static_picture": ["slow", "regions"],
    "inc_glow_breathe": ["slow", "incandescent", "regions"], "inc_slow_wave": ["slow", "incandescent", "regions"],
    "inc_twinkle_bulbs": ["slow", "incandescent", "regions"], "inc_region_wander": ["slow", "incandescent", "regions"],
    "frost_breath": ["slow"], "aurora": ["slow"], "snowfall": ["slow"], "ibiza_sunset": ["slow"], "fire_candle": ["slow", "incandescent", "regions"],
    "fire_embers": ["slow"], "led_breathe": ["slow"], "led_gradient_flow": ["slow"],
    "music_sparkle": ["music"], "music_hold": ["music", "regions"], "music_drop": ["music"], "music_trace": ["music"],
    "music_fill": ["music"], "music_eq": ["music"], "ibiza_strobe": ["music"],
    "mod_ripple": ["geometry"], "snowfall_": [],
}


class Effect:
    def __init__(self, name, kind, label, fn, params, lamp=None, pack="", doc="", regions=False, tags=None):
        self.name, self.kind, self.label, self.fn = name, kind, label, fn
        self.params, self.lamp, self.pack, self.doc, self.regions = params, lamp, pack, doc, regions
        tags = list(tags if tags is not None else DEFAULT_TAGS.get(name, []))
        if regions and "regions" not in tags:
            tags.append("regions")
        if lamp and "incandescent" not in tags:
            tags.append("incandescent")
        self.tags = tags

    def defaults(self):
        return {s.name: s.default for s in self.params}

    def merged(self, params):
        d = self.defaults(); d.update({k: v for k, v in (params or {}).items() if k in d})
        return d

    def json(self):
        return {"name": self.name, "kind": self.kind, "label": self.label, "pack": self.pack,
                "doc": self.doc, "lamp": self.lamp, "regions": self.regions, "tags": self.tags,
                "params": [s.json() for s in self.params]}


REGISTRY = {}


def effect(name, kind, label, params=(), lamp=None, pack="", doc="", regions=False, tags=None):
    def deco(fn):
        REGISTRY[name] = Effect(name, kind, label, fn, list(params), lamp, pack, doc or (fn.__doc__ or "").strip(), regions, tags)
        return fn
    return deco


def registry_json():
    return [e.json() for e in REGISTRY.values()]


# ----------------------------------------------------------------- geometry
class GroupCtx:
    """The props of one group, in world inches. Sorted left -> right by centre x."""

    def __init__(self, gid, placements):
        self.id = gid
        self.props = [PropGeom(pl, i) for i, pl in enumerate(placements)]
        self.props.sort(key=lambda p: p.cx)
        for i, p in enumerate(self.props):
            p.idx = i
        self.P = len(self.props)
        self.ids = [p.id for p in self.props]
        if self.P:
            self.C = np.array([[p.cx, p.cy, p.cz] for p in self.props])
            self.D = np.linalg.norm(self.C[:, None] - self.C[None, :], axis=2)
            xs = np.concatenate([p.wx for p in self.props]); zs = np.concatenate([p.wz for p in self.props])
            ys = np.concatenate([p.wy for p in self.props])
            self.x0, self.x1 = float(xs.min()), float(xs.max())
            self.y0, self.y1 = float(ys.min()), float(ys.max())
            self.z0, self.z1 = float(zs.min()), float(zs.max())
            self.pitch = float(np.median([p.pitch for p in self.props]))
        else:
            self.C = np.zeros((0, 3)); self.D = np.zeros((0, 0))
            self.x0 = self.x1 = self.y0 = self.y1 = self.z0 = self.z1 = 0.0; self.pitch = 1.0
        self.width = max(1.0, self.x1 - self.x0)
        self.height = max(1.0, self.z1 - self.z0)
        # rank 0..1 of each prop left -> right (for walks / chases)
        self.rank = np.linspace(0, 1, self.P) if self.P > 1 else np.zeros(self.P)

    def zeros(self):
        return {p.id: np.zeros((p.n, 3)) for p in self.props}

    def fill(self, rgb):
        rgb = np.asarray(rgb, float)
        return {p.id: np.broadcast_to(rgb, (p.n, 3)).copy() for p in self.props}

    def index_of(self, prop_id, default=None):
        """Index (left->right) of a prop id in this group, or `default` if it is not here."""
        pid = str(prop_id or "")
        if pid in self.ids:
            return self.ids.index(pid)
        for i, p in enumerate(self.props):                     # also accept the label / mod stem
            if pid and pid in (getattr(p.pl, "label", None), getattr(p.pl, "mod", "").replace(".mod", "")):
                return i
        return default

    def feature(self, mode, m, every_bars=4, prop_id=None):
        """Index of the 'feature' prop for multi-prop choreography.
        mode: centre | left end | right end | largest | pass along (changes every `every_bars`)
              | random per phrase | specific prop (the prop with id `prop_id`; centre if it is not in the group)"""
        if not self.P:
            return 0
        if mode == "specific prop":
            k = self.index_of(prop_id)
            return self.P // 2 if k is None else k
        if mode == "left end":
            return 0
        if mode == "right end":
            return self.P - 1
        if mode == "largest":
            return int(np.argmax([p.n for p in self.props]))
        if mode == "pass along":
            return int(m.bar_index // max(1, every_bars)) % self.P
        if mode == "random per phrase":
            return int(np.random.default_rng(int(m.bar_index // max(1, every_bars)) + 17).integers(0, self.P))
        return self.P // 2

    def x01(self, p):
        """per-pixel world x normalised over the group 0..1 (left -> right)"""
        return (p.wx - self.x0) / self.width

    def z01(self, p):
        """per-pixel world height normalised over the group 0..1 (ground -> top)"""
        return (p.wz - self.z0) / self.height


# -------------------------------------------------------------------- music
class Music:
    """The music at one instant. Zeros when no audio clip covers the time."""
    __slots__ = ("t", "ft", "has_audio", "rms", "low", "mid", "high", "perc", "harm", "hit", "hit_high",
                 "energy", "beat_env", "downbeat_env", "beat_phase", "bar_phase", "phrase_phase",
                 "beat_index", "bar_index", "bpm", "beats_per_bar", "beat_len", "on_beat", "on_bar", "pulse", "chroma", "bands", "dt")

    def __init__(self, t, dt=1 / 30.3):
        self.t, self.ft, self.has_audio, self.dt = t, 0.0, False, dt
        for k in ("rms", "low", "mid", "high", "perc", "harm", "hit", "hit_high", "energy", "beat_env", "downbeat_env"):
            setattr(self, k, 0.0)
        self.bpm, self.beats_per_bar, self.beat_len = 120.0, 4, 0.5
        self.beat_phase = (t * 2) % 1.0; self.bar_phase = (t / 2) % 1.0; self.phrase_phase = (t / 8) % 1.0
        self.beat_index = math.floor(t * 2); self.bar_index = math.floor(t / 2)      # floor, not int(): negative local times count down correctly
        self.on_beat = False; self.on_bar = False
        self.pulse = math.exp(-4.0 * self.beat_phase)
        self.chroma = None
        # silence: a synthetic 120 BPM click so music-driven effects still show something without audio
        self.hit = math.exp(-self.beat_phase * 10); self.hit_high = self.hit if self.beat_index % 2 else 0.0
        self.beat_env = math.exp(-self.beat_phase * 4); self.downbeat_env = self.beat_env if self.beat_index % 4 == 0 else 0.0
        self.energy = 0.5 + 0.4 * math.sin(t / 7.0); self.rms = self.energy; self.low = 0.3 + 0.5 * self.hit; self.high = 0.3 + 0.4 * self.hit_high
        # silence: a gentle synthetic EQ so visualisers still move without audio
        self.bands = np.array([0.5 + 0.4 * math.sin(t * (1.3 + 0.37 * k) + k) for k in range(8)]) * 0.5


class AudioClip:
    """One audio clip of the project bound to its analysed Track."""

    def __init__(self, spec, track):
        self.spec, self.track = spec, track
        self.start = float(spec["start"]); self.offset = float(spec.get("offset") or 0.0)
        self.duration = float(spec.get("duration") or track.duration)
        beats, idx, songs = track.grid_songs(spec.get("songs") or [], spec.get("bpm"), spec.get("beat_offset"), spec.get("beats_per_bar") or 4)
        self.beats, self.beat_song, self.songs = np.asarray(beats), np.asarray(idx), songs
        if len(self.beats) < 2:
            self.beats = np.arange(0, track.duration, 60.0 / 120.0); self.beat_song = np.zeros(len(self.beats), int)
            self.songs = [{"from": 0.0, "to": track.duration, "bpm": 120.0, "beats_per_bar": 4}]
        # index of the first beat of each song, for bar counting
        self.song_first = {k: int(np.argmax(self.beat_song == k)) for k in range(len(self.songs)) if (self.beat_song == k).any()}
        # slow energy: rms over ~1 s, normalised 5..95 pct over the clip
        sm = uniform_filter1d(track.rms, AFPS)
        i0, i1 = track.frame(self.offset), max(track.frame(self.offset) + 1, track.frame(self.offset + self.duration))
        lo, hi = np.percentile(sm[i0:i1], 5), np.percentile(sm[i0:i1], 95)
        self.energy = np.clip((sm - lo) / max(1e-6, hi - lo), 0, 1)

    def covers(self, t):
        return self.start <= t < self.start + self.duration

    def music(self, t, fps):
        m = Music(t, 1.0 / fps)
        tr = self.track
        ft = t - self.start + self.offset
        f = tr.frame(ft)
        m.ft, m.has_audio = ft, True
        m.rms, m.low, m.mid, m.high = float(tr.rms[f]), float(tr.low[f]), float(tr.mid[f]), float(tr.high[f])
        m.perc, m.harm, m.hit, m.hit_high = float(tr.perc[f]), float(tr.harm[f]), float(tr.hit[f]), float(tr.hit_high[f])
        m.energy = float(self.energy[f])
        m.beat_env, m.downbeat_env = float(tr.beat_env[f]), float(tr.downbeat_env[f])
        m.chroma = tr.chroma_f[f]
        m.bands = tr.bands[f] if hasattr(tr, "bands") else m.bands
        b = self.beats
        i = int(np.clip(np.searchsorted(b, ft) - 1, 0, len(b) - 2))
        k = int(self.beat_song[i]); sg = self.songs[k]; bpb = int(sg["beats_per_bar"])
        i_song = i - self.song_first.get(k, 0)                     # beats since this song's first beat
        m.beat_len = float(max(1e-3, b[i + 1] - b[i])) if self.beat_song[i + 1] == k else 60.0 / float(sg["bpm"])
        m.beat_phase = float(np.clip((ft - b[i]) / m.beat_len, 0, 1))
        m.beat_index, m.bpm, m.beats_per_bar = i_song, (60.0 / m.beat_len if sg.get("bpm_end") else float(sg["bpm"])), bpb
        m.bar_index = i_song // bpb
        m.bar_phase = ((i_song % bpb) + m.beat_phase) / bpb
        pb = bpb * 4
        m.phrase_phase = ((i_song % pb) + m.beat_phase) / pb
        dt = 1.0 / fps
        m.on_beat = m.beat_phase * m.beat_len < dt
        m.on_bar = m.on_beat and (i_song % bpb == 0)
        m.pulse = math.exp(-4.0 * m.beat_phase)
        return m


# ----------------------------------------------------------------- renderer
BLACK = None


class Renderer:
    def __init__(self, project, layout, fps=30.3, tracks_cache=None):
        self.project, self.layout, self.fps = project, layout, float(fps)
        self.groups = {gid: GroupCtx(gid, layout.in_group(gid)) for gid in layout.groups}
        self.all_props = [p for g in self.groups.values() for p in g.props]
        self._tracks = tracks_cache if tracks_cache is not None else {}
        self.audio = []
        for a in project.audio:
            try:
                tr = self._tracks.get(a["file"]) or Track(a["file"])
                self._tracks[a["file"]] = tr
                if not a.get("duration"):
                    a["duration"] = tr.duration
                self.audio.append(AudioClip(a, tr))
            except Exception as e:                      # missing file: timeline still works, music is silent
                print("audio:", a["file"], e)
        self.reset()

    def reset(self):
        self.state = {}
        self.lamps = {gid: LampBank(g.props, self.fps) for gid, g in self.groups.items()}

    # ---- music
    def music_at(self, t):
        for a in self.audio:
            if a.covers(t):
                return a.music(t, self.fps)
        return Music(t, 1.0 / self.fps)

    # ---- clips
    def _st(self, cid):
        return self.state.setdefault(cid, {})

    def _anim(self, g, m, clip, t, extend=False):
        """Render one animation clip at absolute time t. With extend=True the
        clip keeps running outside its own range (local time may be negative
        or past the end) so a transition can blend two LIVE animations
        instead of a frozen last frame."""
        fx = REGISTRY.get(clip["effect"])
        if fx is None:
            return g.zeros(), None
        pal = PAL.resolve(clip.get("palette"), self.project.d.get("palettes"))
        tl = (t - clip["t0"]) if extend else max(0.0, t - clip["t0"])
        if "_local_shift" in clip:                       # pre-roll for seamless loops (render.py): the clip
            tl = t - clip["t0"] - clip["_local_shift"]   # was pulled earlier; local time runs negative up to 0
        try:
            out = fx.fn(g, m, tl, fx.merged(clip.get("params")), pal, self._st(clip["id"]))
        except Exception as e:                           # a broken effect must not kill the preview
            print(f"effect {fx.name} failed: {e!r}")
            out = g.zeros()
        for p in g.props:
            if p.id not in out:
                out[p.id] = np.zeros((p.n, 3))
        return out, fx

    def group_frame(self, gid, t, m=None):
        g = self.groups[gid]
        m = m or self.music_at(t)
        track = self.project.track_for_group(gid)
        if track is None or not g.P:
            return g.zeros()
        clips = track["clips"]
        anims = [c for c in clips if c["kind"] == "anim"]
        cur = next((c for c in anims if c["t0"] <= t < c["t1"]), None)
        lamp_fx = None
        if cur is not None:
            F, lamp_fx = self._anim(g, m, cur, t)
        else:
            F = g.zeros()
        # transitions: blend from the anim ending at/before the window to the one after
        for tr in (c for c in clips if c["kind"] == "trans" and c["t0"] <= t < c["t1"]):
            fx = REGISTRY.get(tr["effect"])
            if fx is None:
                continue
            u = (t - tr["t0"]) / max(1e-3, tr["t1"] - tr["t0"])
            mid = (tr["t0"] + tr["t1"]) / 2
            # outgoing = the animation playing just before the cut (the cut is the anim boundary
            # inside the window, else the window's midpoint); incoming = the one playing after it.
            cut = next((c["t0"] for c in anims if tr["t0"] < c["t0"] < tr["t1"]), mid)
            prev = [c for c in anims if c["t0"] < cut <= c["t1"] + 0.02]
            nxt = [c for c in anims if c["t0"] <= cut + 0.02 and c["t1"] > cut]
            if prev and nxt and prev[-1] is nxt[0]:                      # transition inside one clip: fade to/from itself
                prev = [c for c in anims if c["t1"] <= cut + 0.02 and c is not nxt[0]][-1:] or []
            # both animations keep RUNNING through the whole window (extend=True), so nothing freezes
            A = self._anim(g, m, prev[-1], t, extend=True)[0] if prev else g.zeros()
            B = self._anim(g, m, nxt[0], t, extend=True)[0] if nxt else g.zeros()
            pm = fx.merged(tr.get("params"))
            uu = float(np.clip(u, 0, 1))
            curve = pm.get("curve", "linear")
            if curve == "ease in-out":
                uu = uu * uu * (3 - 2 * uu)
            elif curve == "ease in":
                uu = uu * uu
            elif curve == "ease out":
                uu = 1 - (1 - uu) ** 2
            pal = PAL.resolve(tr.get("palette"), self.project.d.get("palettes"))
            try:
                F = fx.fn(g, m, uu, pm, pal, A, B, self._st(tr["id"]))
            except Exception as e:
                print(f"transition {fx.name} failed: {e!r}")
        # modifiers stack on top, in time order
        for md in sorted((c for c in clips if c["kind"] == "mod" and c["t0"] <= t < c["t1"]), key=lambda c: c["t0"]):
            fx = REGISTRY.get(md["effect"])
            if fx is None:
                continue
            pal = PAL.resolve(md.get("palette"), self.project.d.get("palettes"))
            try:
                F = fx.fn(g, m, t - md["t0"] - md.get("_local_shift", 0.0), fx.merged(md.get("params")), pal, F, self._st(md["id"]))
            except Exception as e:
                print(f"modifier {fx.name} failed: {e!r}")
        # lamp model of the current animation
        lp = {"lamp": lamp_fx.lamp if (lamp_fx and lamp_fx.lamp) else "led"}
        if cur is not None and lamp_fx is not None:
            pm = lamp_fx.merged(cur.get("params"))
            if pm.get("lamp"):                                   # an effect may expose the lamp model as a slider
                lp["lamp"] = pm["lamp"]
            for k in ("twinkle_frac", "amber", "tau_on", "tau_off"):
                if k in pm:
                    lp[k] = pm[k]
        F = self.lamps[gid].apply(F, t, lp)
        return {k: np.clip(v, 0, 1) for k, v in F.items()}

    def frame(self, t, groups=None):
        m = self.music_at(t)
        out = {}
        for gid in (groups or self.groups):
            out.update(self.group_frame(gid, t, m))
        return out

    # ---- helpers for the UI
    def prop_order(self):
        """[(prop_id, n)] in the order frames are packed for the WebSocket."""
        return [(p.id, p.n) for p in self.all_props]

    def pack(self, frame, gamma=2.2):
        """frame -> bytes, props in prop_order(), perceptual -> 8-bit with gamma."""
        parts = []
        for p in self.all_props:
            v = frame.get(p.id)
            if v is None:
                parts.append(np.zeros(p.n * 3, np.uint8)); continue
            parts.append((np.clip(v, 0, 1) ** gamma * 255 + 0.5).astype(np.uint8).reshape(-1))
        return np.concatenate(parts).tobytes()


# effects register themselves on import
from .fx import transitions, starfield, lavalamp, incandescent, classic, modifiers, static, fire, icesnow, ibiza, techno, musicfx, songs, choreo, classics, fiesta  # noqa: E402,F401


# ------------------------------------------------------------ fx previews
_PREVIEW_MODS = ("47号.mod", "1号.mod", "61号.mod", "27号.mod")     # cross, bell, Santa, snowflake -- one of each shape family


def preview_rig():
    """A small fixed row of library props for the effect-browser previews
    (the bench props: shapes people know). -> GroupCtx"""
    from .. import layout as LAY
    import os
    pls, x = [], 0.0
    for k, mod in enumerate(_PREVIEW_MODS):
        if not os.path.exists(os.path.join(LAY.PROPS_DIR, mod)):
            continue
        s = LAY.prop_shape(mod)
        x += s["w"] / 2 + 10
        pls.append(LAY.Placement(f"p{k}", mod, "preview", x=x, y=0, z=0))
        x += s["w"] / 2
    return GroupCtx("preview", pls)


_preview_cache = {}


def render_preview(name, seconds=3.0, fps=12, palette="classic"):
    """-> (rig, [packed uint8 frames]) for one effect with default params.
    Transitions blend Colour blocks -> Rainbow wave; modifiers sit on Gradient flow."""
    key = (name, seconds, fps, palette)
    if key in _preview_cache:
        return _preview_cache[key]
    fx = REGISTRY[name]
    g = preview_rig()
    pal = PAL.resolve(palette)
    lamps = LampBank(g.props, fps)
    st, stA, stB = {}, {}, {}
    frames = []
    n = int(seconds * fps)
    for f in range(n):
        t = f / fps
        m = Music(t, 1.0 / fps)
        if fx.kind == "anim":
            F = fx.fn(g, m, t, fx.defaults(), pal, st)
        elif fx.kind == "trans":
            A = REGISTRY["led_blocks"].fn(g, m, t, REGISTRY["led_blocks"].defaults(), pal, stA)
            B = REGISTRY["led_rainbow"].fn(g, m, t, REGISTRY["led_rainbow"].defaults(), pal, stB)
            u = ((t - 0.6) / (seconds - 1.2))                      # hold A, transition, hold B
            uu = float(np.clip(u, 0, 1))
            F = fx.fn(g, m, uu, fx.defaults(), pal, A, B, st) if 0 <= u <= 1 else (A if u < 0 else B)
        else:
            base = REGISTRY["led_gradient_flow"].fn(g, m, t, REGISTRY["led_gradient_flow"].defaults(), pal, stA)
            F = fx.fn(g, m, t, fx.defaults(), pal, base, st)
        for p in g.props:
            if p.id not in F:
                F[p.id] = np.zeros((p.n, 3))
        lp = {"lamp": fx.lamp or "led"}
        if fx.kind == "anim" and fx.defaults().get("lamp"):
            lp["lamp"] = fx.defaults()["lamp"]
        F = lamps.apply(F, t, lp)
        frames.append(np.concatenate([(np.clip(F[p.id], 0, 1) * 255 + 0.5).astype(np.uint8).reshape(-1) for p in g.props]).tobytes())
    _preview_cache[key] = (g, frames)
    return g, frames
