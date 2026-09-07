#!/usr/bin/env python3
"""
seed_layout.py -- build the initial assets/layout.json from the group markup.

    python tools/seed_layout.py            # writes assets/layout.json

Groups come from the owner's marked-up contact sheet (2026-09-07): red =
Stars, blue = Snowflakes, purple = Yule, uncircled = Santa's Workshop.
Placement is a first guess only -- each group in a row along the course, a
gap between groups -- meant to be dragged into shape in the layout editor.
Controllers are auto-assigned 4 props each, neighbours together.

Re-running this OVERWRITES layout.json. Once the yard layout has been edited
by hand, edit that file (or use the editor), do not re-seed.
"""

import os, sys
from collections import OrderedDict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from lightshow.layout import Layout, Placement, prop_shape   # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "layout.json")

GROUPS = OrderedDict([
    ("workshop",   {"label": "Santa's Workshop", "prefix": "WS", "palette": "classic",
                    "color": "#e8b04b"}),
    ("snowflakes", {"label": "Snowflakes",       "prefix": "SF", "palette": "frost",
                    "color": "#5fb8ff"}),
    ("stars",      {"label": "Stars",            "prefix": "ST", "palette": "gold",
                    "color": "#ff6b5f"}),
    ("yule",       {"label": "Yule",             "prefix": "YU", "palette": "classic",
                    "color": "#c77dff"}),
])

# (mod stem, label guess). Labels are what the shape looks like on the
# contact sheet -- correct them in layout.json if they are wrong.
MEMBERS = {
    "workshop": [
        ("12号右", "santa with gift (R)"), ("12号左", "santa with gift (L)"),
        ("14号", "santa with sack"), ("9号右", "snowman with broom (R)"),
        ("螺旋圣诞树", "spiral tree"), ("15号", "candy cupcake"),
        ("64号", "bear"), ("61号", "santa waving"), ("65号", "reindeer"),
        ("13号右", "bear waving (R)"), ("13号左", "bear waving (L)"),
        ("63号", "bear sitting"), ("62号", "nutcracker"),
        ("60号", "starburst"), ("1号", "bell"),
    ],
    "yule": [
        ("9号左", "snowman with broom (L)"), ("59号", "burst"),
        ("44号", "starburst"), ("8号", "bow"), ("2号右", "candy cane (R)"),
        ("2号左", "candy cane (L)"), ("6号", "bell with bow"),
        ("7号", "bell with bow"), ("41号", "star tree"), ("50号", "4-point star"),
    ],
    "stars": [
        ("54号", "star"), ("35号", "burst"), ("42号", "burst star"),
        ("49号", "4-point star"), ("16号", "snowflake/star"), ("34号", "burst"),
        ("58号", "star"), ("4号", "candy cane"), ("40号", "4-point star"),
        ("48号", "star"), ("57号", "4-point star"), ("38号", "6-point star"),
        ("39号", "star"), ("47号", "cross snowflake"), ("37号", "5-point star"),
        ("46号", "cross"), ("36号", "star burst"), ("45号", "cross"),
    ],
    "snowflakes": [
        ("56号", "snowflake"), ("32号", "snowflake"), ("33号", "snowflake"),
        ("26号", "snowflake"), ("27号", "snowflake"), ("11号", "christmas tree"),
        ("55号", "wreath snowflake"), ("31号", "snowflake"), ("30号", "snowflake"),
        ("52号", "snowflake"), ("51号", "snowflake"), ("10号", "tree"),
        ("28号", "snowflake"), ("29号", "snowflake"), ("24号", "snowflake"),
        ("25号", "snowflake"), ("20号", "snowflake"), ("21号", "snowflake"),
        ("23号", "snowflake"), ("43号", "starburst"), ("18号", "snowflake"),
        ("19号", "snowflake"), ("17号", "snowflake"), ("22号", "snowflake"),
        ("53号", "star"),
    ],
}

GAP_IN = 30.0            # between neighbouring props in a row
GROUP_GAP_IN = 240.0     # 20 ft between groups along the course


def main():
    L = Layout(groups=GROUPS, meta={"notes": "seeded by tools/seed_layout.py; "
                                             "positions are placeholders"})
    x = 0.0
    ids = set()
    for gid, members in MEMBERS.items():
        for stem, label in members:
            mod = stem + ".mod"
            s = prop_shape(mod)
            x += s["w"] / 2
            pid = stem.replace("号", "").replace("右", "R").replace("左", "L")
            pid = {"螺旋圣诞树": "spiral"}.get(pid, pid)
            assert pid not in ids, pid
            ids.add(pid)
            L.props.append(Placement(id=pid, mod=mod, group=gid, label=label,
                                     x=round(x, 1), y=0.0, z=0.0))
            x += s["w"] / 2 + GAP_IN
        x += GROUP_GAP_IN
    L.auto_assign()
    L.save(OUT)
    print(L.summary())
    print(f"\nwrote {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
