#!/usr/bin/env python3
"""
rgbfile.py -- reader/writer for the "RGB01001" SD-card LED show format
used by low-cost Chinese multi-channel SPI/DMX pixel controllers.

FORMAT (all multi-byte fields BIG-ENDIAN unless noted)
-----------------------------------------------------------------------
off  size  field
0x00  8    magic  b"RGB01001"
0x08  4    0xFFFFFFFF  (constant; likely "no id"/reserved mask)
0x0C  4    LITTLE-endian uint32, looks like a unix timestamp
           (0x5E144A02 = 2020-01-07 09:06:10Z). Not a checksum --
           no CRC/sum over the body matches, so nothing validates it.
0x10  4    total_pixels  (sum of all channel counts)
0x14  2    channel_count
0x16  1    0x01  (version / flags)
0x17  13*N channel records, N = channel_count
0x??  512  LUT: 256 x uint16 BE, identity 0..255 (gamma/brightness table)
0x24B ...  frame data

CHANNEL RECORD (13 bytes)
  +0  2  channel id (0-based)
  +2  2  pixel count for this channel
  +4  9  constant tail 00 00 00 00 04 80 fa 00 50  (identical on every
         channel; per-port config: IC type / color order / max-pixels /
         brightness. Exact split unknown -- copy verbatim.)

FRAME DATA
  frame_size = total_pixels * 3
  frame_count = (filesize - header_size) / frame_size
  Each frame is all channels concatenated in id order, 3 bytes/pixel.
  Channel c occupies pixels [start[c], start[c]+count[c]).

OBSERVED IN Sc-01-01.rgb
  2028 px total = 561 + 210 + 282 + 975 across 4 channels
  1738 frames, exact (no padding, no per-frame headers, no delimiters)
  Byte values only ever 0..127, and only the 16 levels
  round(i*127/15) -- source art was 4-bit/channel at 50% headroom.
"""

import struct, sys, os, time

MAGIC = b"RGB01001"
REC_TAIL = bytes.fromhex("00000000048 0fa0050".replace(" ", ""))
LUT = b"".join(struct.pack(">H", i) for i in range(256))
REC_SIZE = 13


class Show:
    def __init__(self, channels, frames=None, stamp=None,
                 tail=REC_TAIL, version=1, field08=0xFFFFFFFF, field0C=None):
        self.channels = list(channels)          # pixel count per channel
        self.frames = frames if frames is not None else []
        # 0x0C-0D: header_size - 1. Confirmed on 4-, 8- and 24-channel files
        # (586/587, 638/639, 846/847). Derived unless explicitly overridden.
        self._field0C = field0C
        self.tail = tail
        self.version = version
        self.field08 = field08

    # ---- geometry ----
    @property
    def total_px(self):
        return sum(self.channels)

    @property
    def total(self):
        """value stored at 0x10 -- FRAME SIZE IN BYTES, not pixels"""
        return sum(self.channels) * 3

    @property
    def frame_size(self):
        return sum(self.channels) * 3

    @property
    def header_size(self):
        return 0x17 + REC_SIZE * len(self.channels) + 512

    @property
    def field0C(self):
        return self.header_size - 1 if self._field0C is None else self._field0C

    def bounds(self, ch):
        s = sum(self.channels[:ch])
        return s, s + self.channels[ch]

    # ---- read ----
    @classmethod
    def load(cls, path):
        with open(path, "rb") as fh:
            d = fh.read()
        if d[:8] != MAGIC:
            raise ValueError(f"bad magic {d[:8]!r}, expected {MAGIC!r}")
        f08 = struct.unpack_from(">I", d, 0x08)[0]
        f0C = struct.unpack_from(">H", d, 0x0C)[0]      # constant 586
        declared_frames = struct.unpack_from(">H", d, 0x0E)[0]
        total = struct.unpack_from(">I", d, 0x10)[0]
        nch = struct.unpack_from(">H", d, 0x14)[0]
        ver = d[0x16]
        counts, tails = [], []
        for i in range(nch):
            o = 0x17 + REC_SIZE * i
            cid, cnt = struct.unpack_from(">HH", d, o)
            if cid != i:
                raise ValueError(f"channel record {i} has id {cid}")
            if cnt % 3:
                raise ValueError(f"ch{i} byte count {cnt} not divisible by 3")
            counts.append(cnt // 3)      # stored as BYTES -> pixels
            tails.append(d[o + 4:o + 13])
        if sum(counts) * 3 != total:
            raise ValueError(f"channel bytes {sum(counts)*3} != frame size {total}")
        hdr = 0x17 + REC_SIZE * nch
        lut = d[hdr:hdr + 512]
        hdr += 512
        body = d[hdr:]
        fsz = total
        if len(body) % fsz:
            raise ValueError(f"body {len(body)} not divisible by frame {fsz}"
                             f" (remainder {len(body) % fsz})")
        s = cls(counts, tail=tails[0], version=ver, field08=f08)
        expect = 0x17 + REC_SIZE * nch + 512 - 1
        if f0C != expect:
            print(f"  WARNING: 0x0C={f0C}, expected header_size-1={expect}")
            s._field0C = f0C
        s.frames = [body[i * fsz:(i + 1) * fsz] for i in range(len(body) // fsz)]
        s.declared_frames = declared_frames
        if declared_frames != len(s.frames):
            print(f"  WARNING: header declares {declared_frames} frames but file "
                  f"holds {len(s.frames)}")
        s._lut = lut
        s._tails = tails
        return s

    # ---- write ----
    def header(self):
        h = bytearray()
        h += MAGIC
        h += struct.pack(">I", self.field08)
        h += struct.pack(">H", self.field0C)   # 0x0C: constant 586
        h += struct.pack(">H", len(self.frames))  # 0x0E: FRAME COUNT
        h += struct.pack(">I", self.total)
        h += struct.pack(">H", len(self.channels))
        h += bytes([self.version])
        for i, cnt in enumerate(self.channels):
            h += struct.pack(">HH", i, cnt * 3) + self.tail
        h += LUT
        return bytes(h)

    def save(self, path):
        if len(self.frames) > 0xFFFF:
            raise ValueError(f"{len(self.frames)} frames exceeds uint16 field "
                             f"limit of 65535 at 0x0E")
        with open(path, "wb") as f:
            f.write(self.header())
            for fr in self.frames:
                if len(fr) != self.frame_size:
                    raise ValueError("frame wrong size")
                f.write(fr)

    def info(self):
        L = [f"channels={len(self.channels)} px={self.channels}",
             f"total_px={self.total_px}  frame={self.frame_size}B (0x10={self.total})",
             f"frames={len(self.frames)}",
             f"header={self.header_size}B  0x0C={self.field0C} (=hdr-1)"
             f"  frame_count_field={len(self.frames)}",
             f"tail={self.tail.hex(' ')}"]
        for i, c in enumerate(self.channels):
            a, b = self.bounds(i)
            L.append(f"  ch{i}: {c:4d} px  -> pixel[{a}:{b}]  bytes[{a*3}:{b*3}]")
        return "\n".join(L)


# ------------------------------------------------------------------
# authoring helpers
# ------------------------------------------------------------------
def clamp(v, cap=127):
    return 0 if v < 0 else (cap if v > cap else int(v))


class FrameBuf:
    """Mutable one-frame RGB buffer with per-channel addressing."""

    def __init__(self, show, cap=127):
        self.show, self.cap = show, cap
        self.buf = bytearray(show.frame_size)

    def set(self, ch, i, r, g, b):
        a, z = self.show.bounds(ch)
        if not 0 <= i < (z - a):
            return
        o = (a + i) * 3
        c = self.cap
        self.buf[o] = clamp(r, c)
        self.buf[o + 1] = clamp(g, c)
        self.buf[o + 2] = clamp(b, c)

    def fill(self, ch, r, g, b):
        a, z = self.show.bounds(ch)
        for i in range(z - a):
            self.set(ch, i, r, g, b)

    def fill_all(self, r, g, b):
        for ch in range(len(self.show.channels)):
            self.fill(ch, r, g, b)

    def clear(self):
        self.buf = bytearray(self.show.frame_size)

    def bytes(self):
        return bytes(self.buf)


def hsv(h, s=1.0, v=1.0, cap=127):
    h = h % 1.0
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    r, g, b = [(v, t, p), (q, v, p), (p, v, t),
               (p, q, v), (t, p, v), (v, p, q)][i]
    return clamp(r * cap, cap), clamp(g * cap, cap), clamp(b * cap, cap)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("usage: rgbfile.py info FILE | verify FILE")
        return
    cmd = sys.argv[1]
    if cmd == "info":
        print(Show.load(sys.argv[2]).info())
    elif cmd == "verify":
        p = sys.argv[2]
        s = Show.load(p)
        orig = open(p, "rb").read()
        rt = s.header() + b"".join(s.frames)
        print(s.info())
        print("\nround-trip identical:", rt == orig)
        if rt != orig:
            for i, (x, y) in enumerate(zip(rt, orig)):
                if x != y:
                    print(f"  first diff at 0x{i:x}: {x:02x} != {y:02x}")
                    break
        print("LUT is identity:", s._lut == LUT)
        print("all channel tails equal:", len(set(s._tails)) == 1)


if __name__ == "__main__":
    main()
