"""Layout: placement maths, controller packing, hardware limits, export shape."""
import json, os, subprocess, sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from lightshow.layout import (Layout, Placement, MAX_PX_PORT, MAX_PX_UNIT,   # noqa: E402
                              STUB_PX, PORTS)
from lightshow.formats.props import load_mod                               # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
LAYOUT = os.path.join(ROOT, "assets", "layout.json")


def test_mod_files_are_y_down_on_disk_and_y_up_in_memory():
    """The snowman's head (broom handle top) must be the HIGHEST pixel after
    load. On disk the file is y-down, so the loader must flip."""
    raw = json.load(open(os.path.join(ROOT, "assets", "props", "9号右.mod"), encoding="utf-8"))
    p = load_mod(os.path.join(ROOT, "assets", "props", "9号右.mod"))
    ys_disk = [d["y"] for d in raw["dots"]]
    ys_mem = [xy[1] for xy in p.xy]
    assert max(ys_mem) == -min(ys_disk)
    # spot check: the two pixels with the smallest disk-y are the highest in memory
    i = int(np.argmin(ys_disk))
    assert ys_mem[i] == max(ys_mem)


def test_seed_layout_covers_every_prop_once_and_validates():
    L = Layout.load(LAYOUT)
    mods = sorted(f for f in os.listdir(os.path.join(ROOT, "assets", "props")) if f.endswith(".mod"))
    assert sorted(p.mod for p in L.props) == mods            # all 68, none twice
    assert len({p.id for p in L.props}) == len(L.props)
    assert L.total_px() == 16349
    assert not [m for lvl, m in L.validate() if lvl == "error"]


def test_world_transform_rotation_mirror_and_height():
    p = Placement("t", "47号.mod", "g", x=100, y=50, z=24)
    W = p.world()
    assert W[:, 2].min() == pytest.approx(24)                # bottom edge at z
    assert W[:, 0].mean() == pytest.approx(100, abs=0.5)      # centred on x
    assert np.allclose(W[:, 1], 50)                           # rot 0 -> flat in y
    p.rot = 90
    W90 = p.world()
    assert np.allclose(W90[:, 0], 100, atol=1e-9)             # now flat in x
    assert np.ptp(W90[:, 1]) == pytest.approx(np.ptp(W[:, 0]))
    p.rot = 0
    p.mirror = True
    assert np.allclose(p.world()[:, 0], 2 * 100 - W[:, 0])    # mirrored about centre


def test_auto_assign_respects_limits_and_groups():
    L = Layout.load(LAYOUT)
    L.auto_assign()
    rigs = L.controller_rigs()
    for cid, rig in rigs.items():
        assert rig.total_px() <= MAX_PX_UNIT
        assert len(rig.ports) == PORTS
        assert all(pr.n <= MAX_PX_PORT for pr in rig.ports)
        assert len(L.group_of_controller(cid)) == 1           # never across groups
        assert all(ch == STUB_PX or ch > 0 for ch in rig.channels())
    # neighbours together: props on one controller are consecutive along x
    for cid, rig in rigs.items():
        xs = sorted(p.x for p in rig.props())
        gid = next(iter(L.group_of_controller(cid)))
        allx = sorted(p.x for p in L.in_group(gid))
        i = allx.index(xs[0])
        assert allx[i:i + len(xs)] == xs
    assert not [m for lvl, m in L.validate() if lvl == "error"]


def test_validate_catches_double_booked_port_and_oversize_unit():
    L = Layout.load(LAYOUT)
    a, b = L.props[0], L.props[1]
    b.controller, b.port = a.controller, a.port
    msgs = [m for lvl, m in L.validate() if lvl == "error"]
    assert any("both" in m for m in msgs)
    L = Layout.load(LAYOUT)
    big = sorted(L.props, key=lambda p: -p.n)[:8]             # 8 x ~550 px > 4096
    for k, p in enumerate(big):
        p.controller, p.port = "X01", (k % 4) + 1
    assert any("exceeds 4096" in m for lvl, m in L.validate())


def test_round_trip_json():
    L = Layout.load(LAYOUT)
    d = L.to_json()
    L2 = Layout(d["groups"], [Placement(**{k: v for k, v in p.items() if k in Placement.FIELDS})
                              for p in d["props"]], d["controllers"], meta={"notes": d["notes"]})
    assert L2.to_json() == d


def test_build_cards_same_frame_count_and_stubs(tmp_path):
    out = tmp_path / "cards"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_cards.py"),
                        "--seconds", "0.5", "--out", str(out), "--only", "WS04", "SF07"],
                       capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "src"})
    assert r.returncode == 0, r.stderr
    man = json.load(open(out / "manifest.json"))
    assert set(man["cards"]) == {"WS04", "SF07"}
    assert {c["frames"] for c in man["cards"].values()} == {man["frames"]}
    assert man["cards"]["SF07"]["channels"] == [115, 32, 32, 32]      # stubs
    from lightshow.formats.rgbfile import Show
    s = Show.load(str(out / man["cards"]["SF07"]["file"]))
    assert s.channels == [115, 32, 32, 32] and len(s.frames) == man["frames"]
    # spatially varied, never uniform
    f = np.frombuffer(s.frames[-1], np.uint8)[:115 * 3].reshape(-1, 3)
    assert len({tuple(px) for px in f}) > 3
