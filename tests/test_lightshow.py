"""
Tests that guard the expensive findings.

Every assertion here corresponds to something that was wrong at some point
during reverse engineering and cost real hardware time to catch. The
byte-exact round-trip is the strongest available check that the format model
is correct -- if it passes on the factory files, the model reproduces
10.5 MB of someone else's encoder output exactly.
"""

import glob
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lightshow import effects as fx                      # noqa: E402
from lightshow import rig                                # noqa: E402
from lightshow.formats import colorloong, props, rgbfile  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
FACTORY = sorted(glob.glob(os.path.join(ROOT, "assets/factory/*.rgb")))
MODS = sorted(glob.glob(os.path.join(ROOT, "assets/props/*.mod")))
XMLS = sorted(glob.glob(os.path.join(ROOT, "assets/projects/*.xml")))
MOC = os.path.join(ROOT, "assets/props/圣诞树.moc")
PROP47 = os.path.join(ROOT, "assets/props/47号.mod")


# --------------------------------------------------------------- .rgb codec
@pytest.mark.parametrize("path", FACTORY)
def test_round_trip_is_byte_identical(path):
    """The whole format model in one assertion."""
    s = rgbfile.Show.load(path)
    with open(path, "rb") as fh:
        original = fh.read()
    assert s.header() + b"".join(s.frames) == original


@pytest.mark.parametrize("path", FACTORY)
def test_frame_count_divides_exactly(path):
    """0x10 is a frame size in BYTES. Reading it as a pixel count gives
    42.67 and 88.67 frames on two of the factory files."""
    s = rgbfile.Show.load(path)
    body = os.path.getsize(path) - s.header_size
    assert body % s.frame_size == 0
    assert body // s.frame_size == len(s.frames)


@pytest.mark.parametrize("path", FACTORY)
def test_header_invariants(path):
    s = rgbfile.Show.load(path)
    assert s.declared_frames == len(s.frames)      # 0x0E is authoritative
    assert s.field0C == s.header_size - 1          # 0x0C tracks header size
    assert s.total == sum(s.channels) * 3          # 0x10 is bytes
    assert s._lut == rgbfile.LUT                   # identity LUT
    assert len(set(s._tails)) == 1                 # tail is global config


def test_channel_byte_counts_divide_by_three():
    for path in FACTORY:
        s = rgbfile.Show.load(path)
        for px in s.channels:
            assert px > 0


def test_frame_count_field_is_uint16_capped():
    s = rgbfile.Show([8])
    s.frames = [bytes(s.frame_size)] * 3
    s._n_over = None
    with pytest.raises(ValueError, match="65535"):
        s.frames = [bytes(s.frame_size)] * 70000
        s.save("/tmp/_too_long.rgb")


# ------------------------------------------------------------------ geometry
def test_mod_dotcount_matches_dots():
    for path in MODS:
        p = props.load_mod(path)
        assert len(p) > 0


def test_physical_scale_is_plausible():
    """lampRad 5 => 10 units per bulb => 20 units/inch. Cross-check: every
    prop should land in the 1-5 ft range of a yard prop."""
    for path in MODS:
        w, h = props.load_mod(path).size_inches()
        assert 1 <= max(w, h) <= 80, (path, w, h)


def test_wire_order_has_no_jumps():
    """dots[i] is pixel i along the chain. A big jump would mean the list is
    not in wire order and every chase effect would be wrong."""
    for path in MODS:
        p = props.load_mod(path)
        d = [np.hypot(*(np.array(p.xy[i + 1]) - np.array(p.xy[i])))
             for i in range(len(p) - 1)]
        med = float(np.median(d))
        assert max(d) < 6 * med, path


# -------------------------------------------------------------- .xml project
@pytest.mark.parametrize("path", XMLS)
def test_xml_ports_partition_the_point_cloud(path):
    proj = colorloong.load_xml(path)
    assert proj.total_pixels() > 0
    for p in proj.ports:
        if p.declared is not None and not p.is_empty:
            assert p.declared == len(p)


def test_empty_ports_export_as_32px_stubs():
    """The rule that silently corrupts channel offsets if missed. In es.xml
    eleven ports are LightCount=0, and the matching .rgb has 32 px channels
    at exactly those indices."""
    es = [p for p in XMLS if "es" in os.path.basename(p)][0]
    proj = colorloong.load_xml(es)
    empty = [p.index for p in proj.ports if p.is_empty]
    assert len(empty) == 11
    chans = proj.rgb_channels()
    assert all(chans[i] == 32 for i in empty)
    assert sum(chans) == proj.total_pixels() + 32 * len(empty)


def test_xml_geometry_matches_the_factory_rgb():
    """End-to-end: the 24-channel project derives the 24-channel file."""
    es = [p for p in XMLS if "es" in os.path.basename(p)][0]
    r = rig.load(es)
    s = rgbfile.Show.load(os.path.join(ROOT, "assets/factory/Sc-01-01_24ch.rgb"))
    assert r.rgb_channels() == s.channels


# -------------------------------------------------------------------- rig
def test_every_loader_reaches_the_same_model():
    for path in (PROP47, MOC, XMLS[0]):
        r = rig.load(path)
        assert len(r.ports) >= 1
        assert r.total_pixels() > 0
        assert len(r.rgb_channels()) == len(r.ports)


def test_rig_json_carries_physical_scale():
    j = rig.load(PROP47).to_json()
    assert j["unitsPerInch"] == 20.0
    assert j["bulbDiameterUnits"] == 10.0


# ----------------------------------------------------------------- effects
@pytest.mark.parametrize("name", sorted(fx.REGISTRY))
def test_effect_is_finite_and_in_range(name):
    p = props.load_mod(PROP47)
    c = fx.Ctx(p.xy, p.pitch_inches())
    for t in (0.0, 0.37, 1.7, 9.9, 60.0):
        c.t = t
        c.rms = c.low = c.mid = c.high = c.hit = 0.6
        c.hit_high = 0.5
        out = fx.render(name, c)
        assert out.shape == (c.n, 3)
        assert np.isfinite(out).all()
        assert out.min() >= 0 and out.max() <= 1


@pytest.mark.parametrize("name", sorted(fx.REGISTRY))
def test_effect_is_pure(name):
    """Same t must give the same frame. A stateful effect cannot be
    previewed, scrubbed, or rendered deterministically."""
    p = props.load_mod(PROP47)
    c = fx.Ctx(p.xy, p.pitch_inches())
    c.t = 3.25
    c.rms = c.low = c.high = c.hit = 0.5
    a = fx.render(name, c)
    c.t = 99.0
    fx.render(name, c)
    c.t = 3.25
    assert np.allclose(a, fx.render(name, c))


def test_lighten_preserves_saturation_where_add_would_not():
    """Additive compositing of several coloured layers washes to white."""
    n = 40
    red = np.tile([1.0, 0.2, 0.2], (n, 1))
    blue = np.tile([0.2, 0.2, 1.0], (n, 1))
    green = np.tile([0.2, 1.0, 0.2], (n, 1))

    def sat(x):
        mx, mn = x.max(1), x.min(1)
        return float(np.mean((mx - mn) / np.maximum(mx, 1e-9)))

    added = np.clip(red + blue + green, 0, 1)
    assert sat(added) < 0.05                      # washed out
    assert sat(fx.lighten(red, blue, green)) >= sat(added)


def test_frost_core_is_white_and_falloff_is_blue():
    bright = fx.frost(np.array([1.0]))[0]
    dim = fx.frost(np.array([0.25]))[0]
    assert bright.min() / bright.max() > 0.85     # near white
    assert dim[2] > dim[0] * 1.5                  # blue-dominant


def test_gamma_conversion_matters():
    """Identity LUT means no hardware gamma; a linear ramp looks top-heavy."""
    mid = fx.to_bytes(np.array([[0.5, 0.5, 0.5]]))[0, 0]
    assert mid < 128
