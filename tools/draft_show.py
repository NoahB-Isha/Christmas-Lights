#!/usr/bin/env python3
"""
draft_show.py -- turn markers.json + per-song analysis into a first show.yaml.

    python tools/draft_show.py            # -> assets/show/show.yaml (refuses to overwrite)
    python tools/draft_show.py --force    # overwrite

show.yaml is the AUTHORING file for the music show (docs/09-SHOW-DESIGN.md
§5): one entry per song, one per marked section, each with the owner's note,
intensity, palette and a `look`. The draft picks looks from keywords in the
notes; they are starting points to be edited by hand or by an AI, not
decisions. After the first run, edit show.yaml directly -- re-running this
would discard those edits.
"""
import argparse, json, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

LOOKS = {   # name -> what it means; the renderer will implement these
    "starfield":    "mostly dark; single bulbs pop on onsets and cool out (frost); a few whole props twinkle in/out",
    "pulse":        "whole-prop breathing on the beat, group colour, low amplitude",
    "build":        "brightness and sparkle density ramp toward the next marker",
    "hold-breath":  "everything drops to a dim ember; one feature prop holds; ends on the next marker",
    "drop":         "everything: full palette, course-wide wave on downbeats, sparkle on hits, arm/ray chases",
    "wave":         "slow colour waves travelling along the course, per-group hue, bass sets the width",
    "conversation": "call and response between two sub-groups, phrase-locked to bars",
    "feature":      "one prop (or one group) carries the melody; others dim to a floor and ripple when it hits",
    "chase":        "wire-order chases and radial rings on the beat, mid-bright",
    "ornaments":    "steady group wash with pixel-cluster ornaments twinkling gold/red/blue",
    "shimmer":      "always-on low-density twinkle, no beat; used for intros, tails and fades",
    "fade":         "current look decays to embers over the section",
    "change-up":    "keep the family, re-roll variation seed, rotate palette",
}

KEYWORDS = [   # (regex, look) -- order matters: first match wins
    (r"pause|stop", "hold-breath"), (r"fade", "fade"), (r"build|pick", "build"),
    (r"outro|finish|ends|resumes", "wave"), (r"drop", "drop"),
    (r"starfield|pluck|piccato", "starfield"), (r"solo", "feature"),
    (r"vocal|chorus|ladies|gent|words|harmony", "conversation"),
    (r"drum|beat comes|first .*hit", "pulse"), (r"horn|piano|guitar|violin|melody", "feature"),
]

SONG_PALETTE = {   # keyword in song label -> default palette per group
    "bells":     {"snowflakes": "frost", "stars": "white-gold", "workshop": "frost", "yule": "frost"},
    "sugarplum": {"snowflakes": "violet-ice", "stars": "violet-ice", "workshop": "violet-ice", "yule": "violet-ice"},
    "jingle":    {"snowflakes": "frost", "stars": "gold", "workshop": "classic", "yule": "classic"},
    "rockin":    {"snowflakes": "classic", "stars": "gold", "workshop": "classic", "yule": "classic"},
    "snowman":   {"snowflakes": "frost", "stars": "white", "workshop": "frost", "yule": "frost"},
    "feliz":     {"snowflakes": "fiesta", "stars": "gold", "workshop": "fiesta", "yule": "fiesta"},
    "accapela":  {"snowflakes": "frost", "stars": "white-gold", "workshop": "classic", "yule": "classic"},
}


def mmss(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def look_for(label, is_first):
    if is_first:
        return "starfield" if re.search(r"starfield|pluck", label, re.I) else "pulse"
    for rx, lk in KEYWORDS:
        if re.search(rx, label, re.I):
            return lk
    return "change-up"


def yq(s):
    return json.dumps(s, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    out = os.path.join(ROOT, "assets", "show", "show.yaml")
    if os.path.exists(out) and not a.force:
        sys.exit(f"{os.path.relpath(out, ROOT)} exists -- edit it, or pass --force to regenerate")
    songs = json.load(open(os.path.join(ROOT, "out", "songs.json")))["songs"]

    L = ["# show.yaml -- the music show, authored in seconds. See docs/09-SHOW-DESIGN.md §5.",
         "# Times and notes come from assets/show/markers.json (the owner's listening notes).",
         "# `look` names are defined under `looks:`; edit freely -- the renderer reads this file.",
         "# intensity: 0-10 (null = let the analysis decide). palette: per-group defaults per song.",
         "",
         "audio: assets/audio/show16.mp3", "fps: 60", "layout: assets/layout.json",
         "markers: assets/show/markers.json", "songs_analysis: out/songs.json   # per-song beat grids (make songs)",
         "", "defaults:", "  transition_s: 1.5", "  floor: 0.06          # nothing ever goes fully dark",
         "  shimmer: true        # always-on low-density twinkle under everything", "",
         "palettes:",
         "  frost:       {hues: [0.52, 0.60, 0.68], white_core: true}",
         "  white-gold:  {hues: [0.11, 0.13], white_core: true, sat_max: 0.6}",
         "  gold:        {hues: [0.10, 0.12, 0.14], sat_max: 0.9}",
         "  classic:     {hues: [0.00, 0.33, 0.12], notes: 'red, green (needs hardware tuning), gold'}",
         "  violet-ice:  {hues: [0.70, 0.78, 0.55], white_core: true}",
         "  fiesta:      {hues: [0.00, 0.08, 0.15, 0.33], sat_max: 1.0}",
         "  white:       {hues: [0.60], sat_max: 0.15}",
         "", "looks:"]
    for k, v in LOOKS.items():
        L.append(f"  {k}: {yq(v)}")
    L += ["", "songs:"]
    for s in songs:
        pal = next((p for k, p in SONG_PALETTE.items() if k in s["label"].lower()), None) or \
            {"snowflakes": "frost", "stars": "gold", "workshop": "classic", "yule": "classic"}
        bpm = s["bpm"]
        hint = f"{bpm} detected" + (" (probably half-time: try x2)" if bpm < 80 else "")
        L += [f"  - name: {yq(s['label'].strip())}",
              f"    from: {mmss(s['start'])}", f"    to: {mmss(s['end'])}",
              f"    tempo_hint: {yq(hint)}",
              f"    palette: {json.dumps(pal)}",
              "    sections:"]
        first = {"t": s["start"], "label": s["label"], "intensity": s.get("intensity"), "palette": None}
        for k, sec in enumerate([first] + s["sections"]):
            lk = look_for(sec["label"] or "", k == 0)
            L.append(f"      - at: {mmss(sec['t'])}")
            L.append(f"        look: {lk}")
            L.append(f"        intensity: {'null' if sec.get('intensity') is None else sec['intensity']}")
            if sec.get("palette"):
                L.append(f"        palette: {sec['palette']}")
            if (sec["label"] or "").strip():
                L.append(f"        note: {yq(sec['label'].strip())}")
        L.append("")
    open(out, "w", encoding="utf-8").write("\n".join(L))
    print(f"wrote {os.path.relpath(out, ROOT)}  ({len(songs)} songs, "
          f"{sum(1 + len(s['sections']) for s in songs)} sections)")


if __name__ == "__main__":
    main()
