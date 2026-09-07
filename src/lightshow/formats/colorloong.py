#!/usr/bin/env python3
"""
colorloong.py -- read Colorloong / FastLED.exe .xml project files.

STRUCTURE (XML, CRLF, attribute-only elements)

<Colorloong>
  <PointRadius Radius="1"/>
  <DxfMark Mark="1"/>
  <PointShapeList Count="N">          the whole canvas point cloud
    <PointShape Model=".." TotalNum=".." VerticalNum=".." HorizontalNum=".."
                Left=".." Top=".." Right=".." Bottom=".."/>
  </PointShapeList>
  <BufferCardList Count="P">          one BufferCard == one OUTPUT PORT
    <BufferCard LightModel="通用IC" LightCount="247">
      <Rect SortModel="6" Left Top Right Bottom
            ShapeRadian ShapeMode ShapeAngleCount/>   one per pixel, WIRE ORDER
    </BufferCard>
  </BufferCardList>
  <SceneList Count="1">
    <LayerList Count="L">
      <Layer LayName=".." LayerNum="..">
        <ShapeList/> <EffectList Count="1"><Effect .../></EffectList>
      </Layer>
  <LightModels>                       library of 13 IC types
    <Light PinCount="3" Name="通用IC" IC="7" .../>   4x <PinControl> each
  <WriteToSDList Count="0"/>           SD-card export assignments (empty here)

FACTS ESTABLISHED

* Rect centre == the matching PointShape position; each Rect is a 2x2 box.
* The BufferCards exactly partition the PointShapeList (verified: union of
  703 card-rect centres == the 703 PointShapes, as sets).
* Canvas coordinates are INTEGER and y-DOWN (screen convention), unlike
  .mod/.moc, which props.py also flips to y-UP. This loader flips y so everything internal is
  y-up.
* LightCount == the .rgb channel pixel count for that port.
* >>> LightCount="0" (no prop assigned) EXPORTS AS A 32-PIXEL STUB in the
  .rgb. Verified on the 24-port project: zeros at ports
  [5,8,9,11,12,13,15,16,19,21,23] and the .rgb has 32 px channels at
  exactly those indices; 2555 + 11*32 = 2907 = the .rgb frame total.
  Any exporter MUST reproduce this or channel offsets will shift.

The three sample projects correspond to decoded .rgb files:
    example3.xml  4 ports  247/179/179/98            = 703 px
    example.xml   8 ports  176/179/193/193/193/157/70/247 = 1408 px
    es.xml       24 ports  (11 empty)                = 2555 px -> 2907 exported
"""

import re, os

STUB_PIXELS = 32          # what an unassigned port becomes on export
DEFAULT_LIGHT_MODEL = "通用IC"      # "generic IC"

_CARD = re.compile(r'<BufferCard LightModel="([^"]*)" LightCount="(\d+)"\s*>(.*?)</BufferCard>', re.S)
_RECT = re.compile(r'<Rect [^>]*?Left="(-?\d+)" Top="(-?\d+)" Right="(-?\d+)" Bottom="(-?\d+)"')
_LIGHT = re.compile(r'<Light ([^>]*)>')
_ATTR = re.compile(r'(\w+)="([^"]*)"')


class Port:
    def __init__(self, index, pixels, light_model=DEFAULT_LIGHT_MODEL,
                 declared=None, name=None):
        self.index = index
        self.pixels = pixels               # [(x, y)] y-UP, wire order
        self.light_model = light_model
        self.declared = declared           # LightCount as written
        self.name = name or f"port{index}"

    def __len__(self):
        return len(self.pixels)

    @property
    def is_empty(self):
        return len(self.pixels) == 0

    @property
    def export_pixels(self):
        """pixel count this port occupies in an exported .rgb"""
        return STUB_PIXELS if self.is_empty else len(self.pixels)

    @property
    def bounds(self):
        if not self.pixels:
            return (0, 0, 0, 0)
        xs = [p[0] for p in self.pixels]; ys = [p[1] for p in self.pixels]
        return min(xs), min(ys), max(xs), max(ys)


class Project:
    def __init__(self, name, ports, light_models=None, layers=None):
        self.name = name
        self.ports = ports
        self.light_models = light_models or []
        self.layers = layers or []

    # ---- geometry ----
    @property
    def bounds(self):
        pts = [p for pt in self.ports for p in pt.pixels]
        if not pts:
            return (0, 0, 1, 1)
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def total_pixels(self):
        return sum(len(p) for p in self.ports)

    # ---- .rgb export geometry ----
    def rgb_channels(self):
        """Pixel counts for rgbfile.Show(), with empty ports as 32 px stubs.
        This is what the factory exporter does -- match it exactly."""
        return [p.export_pixels for p in self.ports]

    def rgb_frame_bytes(self):
        return sum(self.rgb_channels()) * 3

    def summary(self):
        ch = self.rgb_channels()
        empt = [p.index for p in self.ports if p.is_empty]
        L = [f"{self.name}: {len(self.ports)} ports, "
             f"{self.total_pixels()} real px",
             f"  rgb channels {ch}",
             f"  frame {self.rgb_frame_bytes()} B "
             f"({sum(ch)} px incl. {len(empt)} stub port(s))"]
        if empt:
            L.append(f"  empty ports -> 32 px stubs at {empt}")
        for p in self.ports:
            x0, y0, x1, y1 = p.bounds
            tag = "EMPTY (stub 32)" if p.is_empty else f"{len(p):4d} px"
            L.append(f"   port{p.index:2d}: {tag:>15s}  "
                     f"bbox {x1-x0:4.0f} x {y1-y0:4.0f}  [{p.light_model}]")
        return "\n".join(L)


def load_xml(path):
    """Parse a Colorloong .xml project. Coordinates returned y-UP."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        s = fh.read()

    ports = []
    for i, m in enumerate(_CARD.finditer(s)):
        model, declared, body = m.group(1), int(m.group(2)), m.group(3)
        px = [((int(a) + int(c)) / 2.0, -(int(b) + int(d)) / 2.0)   # flip y
              for a, b, c, d in _RECT.findall(body)]
        if declared != len(px):
            print(f"  WARNING {os.path.basename(path)} port{i}: "
                  f"LightCount={declared} but {len(px)} rects")
        ports.append(Port(i, px, model, declared))

    models = []
    for m in _LIGHT.finditer(s):
        a = dict(_ATTR.findall(m.group(1)))
        models.append({"name": a.get("Name"), "ic": a.get("IC"),
                       "pins": a.get("PinCount")})

    layers = []
    for m in re.finditer(r'<Layer LayName="([^"]*)" LayerNum="(\d+)"', s):
        layers.append({"name": m.group(1), "num": int(m.group(2))})

    return Project(os.path.basename(path), ports, models, layers)


if __name__ == "__main__":
    import sys, glob
    args = sys.argv[1:] or ["."]
    files = []
    for a in args:
        files += glob.glob(os.path.join(a, "*.xml")) if os.path.isdir(a) else [a]
    for f in sorted(files):
        p = load_xml(f)
        print(p.summary())
        if p.light_models:
            print(f"  IC library ({len(p.light_models)}): "
                  + ", ".join(m["name"] for m in p.light_models[:6]) + " ...")
        print()
