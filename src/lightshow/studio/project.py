"""
project.py -- the timeline project file (assets/studio/project.json).

Everything the editor changes lives here except prop placement (layout.json)
and paint regions (assets/paint/*.json), which keep their own files so the
older tools still read them.

    {
      "version": 1, "name": "Yard show", "layout": "assets/layout.json",
      "fps": 30.3,                       # 60 or 30.3 -- see server.FPS_HELP
      "audio": [ {id, file, name, start, offset, duration, bpm, beats_per_bar,
                  beat_offset, transition: {type, dur}} ],
      "sections": [ {id, t0, t1, label, audio} ],
      "tracks": [ {id, group, clips: [ {id, kind, effect, t0, t1, params, palette} ]} ],
      "palettes": { custom_id: {name, colors} },
      "cards": { controller_id: {sd_label, formatted, written, notes} }
    }

Times are TIMELINE seconds. `kind` is "anim" | "trans" | "mod". Clip params
are the effect's slider values; missing ones take the effect defaults.

Rules the model enforces
  * one audio lane, clips sequential (no stacking): add_audio() appends after the last clip
  * anim clips on one track never overlap: placing one trims or splits its neighbours
  * transitions and modifiers may overlap anything
"""

import json, os, uuid
from collections import OrderedDict

VERSION = 1
KINDS = ("anim", "trans", "mod")


def new_id(prefix="c"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class Project:
    def __init__(self, data=None, path=None):
        self.d = data or {}
        self.path = path
        self.d.setdefault("version", VERSION)
        self.d.setdefault("name", "Yard show")
        self.d.setdefault("layout", "assets/layout.json")
        self.d.setdefault("fps", 30.3)
        self.d.setdefault("audio", [])
        self.d.setdefault("sections", [])
        self.d.setdefault("tracks", [])
        self.d.setdefault("palettes", {})
        self.d.setdefault("cards", {})

    # --------------------------------------------------------------- io
    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh), path)

    @classmethod
    def default(cls, path, layout_rel, groups, audio_file=None, audio_duration=None):
        p = cls({"layout": layout_rel}, path)
        for gid, g in groups.items():
            p.ensure_track(gid)
        if audio_file:
            p.add_audio(audio_file, duration=audio_duration)
        return p

    def save(self, path=None):
        path = path or self.path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.d, fh, ensure_ascii=False, indent=1)
        return path

    def to_json(self):
        return self.d

    # ------------------------------------------------------------ audio
    @property
    def audio(self):
        return self.d["audio"]

    def duration(self):
        ends = [a["start"] + a["duration"] for a in self.audio if a.get("duration")]
        clip_ends = [c["t1"] for t in self.d["tracks"] for c in t["clips"]]
        return max(ends + clip_ends + [60.0])

    def add_audio(self, file, name=None, duration=None, bpm=None):
        start = max([a["start"] + (a.get("duration") or 0) for a in self.audio] + [0.0])
        a = OrderedDict(id=new_id("a"), file=file, name=name or os.path.basename(file),
                        start=round(start, 3), offset=0.0, duration=duration, bpm=bpm,
                        beats_per_bar=4, beat_offset=None, songs=[],
                        transition={"type": "crossfade", "dur": 1.0})
        self.audio.append(a)
        return a

    def audio_at(self, t):
        for a in self.audio:
            if a["start"] <= t < a["start"] + (a.get("duration") or 0):
                return a
        return None

    def relayout_audio(self):
        """Keep audio clips sequential and gap-free in list order."""
        t = 0.0
        for a in self.audio:
            a["start"] = round(t, 3)
            t += a.get("duration") or 0

    # ----------------------------------------------------------- tracks
    def ensure_track(self, gid):
        for t in self.d["tracks"]:
            if t["group"] == gid:
                return t
        t = OrderedDict(id=new_id("t"), group=gid, clips=[])
        self.d["tracks"].append(t)
        return t

    def track(self, tid):
        for t in self.d["tracks"]:
            if t["id"] == tid:
                return t
        raise KeyError(tid)

    def track_for_group(self, gid):
        for t in self.d["tracks"]:
            if t["group"] == gid:
                return t
        return None

    def find_clip(self, cid):
        for t in self.d["tracks"]:
            for c in t["clips"]:
                if c["id"] == cid:
                    return t, c
        raise KeyError(cid)

    def add_clip(self, tid, kind, effect, t0, t1, params=None, palette=None):
        if kind not in KINDS:
            raise ValueError(kind)
        t = self.track(tid)
        c = OrderedDict(id=new_id("c"), kind=kind, effect=effect, t0=float(t0), t1=float(t1),
                        params=params or {}, palette=palette or "classic")
        t["clips"].append(c)
        if kind == "anim":
            self._resolve_overlaps(t, c)
        t["clips"].sort(key=lambda z: (z["kind"], z["t0"]))
        return c

    def update_clip(self, cid, patch):
        t, c = self.find_clip(cid)
        for k, v in patch.items():
            if k in ("t0", "t1"):
                c[k] = float(v)
            elif k == "params":
                c["params"].update(v or {})
            elif k in ("effect", "palette", "kind"):
                c[k] = v
        if c["t1"] <= c["t0"] + 0.05:
            c["t1"] = c["t0"] + 0.05
        if c["kind"] == "anim":
            self._resolve_overlaps(t, c)
        t["clips"].sort(key=lambda z: (z["kind"], z["t0"]))
        return c

    def delete_clip(self, cid):
        t, c = self.find_clip(cid)
        t["clips"].remove(c)

    def _resolve_overlaps(self, track, c):
        """Anim clips never overlap. The clip being placed wins; neighbours
        are trimmed, and one fully covered is removed."""
        keep = []
        for o in track["clips"]:
            if o is c or o["kind"] != "anim":
                keep.append(o); continue
            if o["t1"] <= c["t0"] or o["t0"] >= c["t1"]:
                keep.append(o); continue
            if o["t0"] < c["t0"] and o["t1"] > c["t1"]:
                # split: left part stays, right part becomes a copy
                right = OrderedDict(o); right["id"] = new_id("c"); right["t0"] = c["t1"]
                right["params"] = dict(o["params"])
                o["t1"] = c["t0"]
                keep.append(o); keep.append(right); continue
            if o["t0"] < c["t0"]:
                o["t1"] = c["t0"]
            elif o["t1"] > c["t1"]:
                o["t0"] = c["t1"]
            else:
                continue                                    # fully covered -> dropped
            if o["t1"] - o["t0"] > 0.05:
                keep.append(o)
        track["clips"] = keep

    # --------------------------------------------------------- sections
    def set_sections(self, secs):
        self.d["sections"] = [OrderedDict(id=s.get("id") or new_id("s"), t0=float(s["t0"]), t1=float(s["t1"]),
                                          label=s.get("label", ""), audio=s.get("audio")) for s in secs]

    # ------------------------------------------------------------ cards
    def card(self, cid):
        return self.d["cards"].setdefault(cid, OrderedDict(sd_label=cid, formatted=None, written=None, notes=""))
