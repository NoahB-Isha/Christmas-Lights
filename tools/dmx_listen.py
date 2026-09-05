#!/usr/bin/env python3
"""
dmx_listen.py -- receive DMX512 on a USB-serial (RS-485) adapter and log it.

    python tools/dmx_listen.py --list                 # what adapters exist
    python tools/dmx_listen.py /dev/tty.usbserial-X out/capture.csv
    python tools/dmx_listen.py --selftest             # framing logic, no hw

Output is CSV that feeds straight into tools/dmx_diff.py.

WILL THIS WORK WITH MY DONGLE?

Only if it is a USB-to-SERIAL adapter (FTDI, CH340, CP210x, PL2303) wired to
RS-485. A USB-to-ETHERNET adapter cannot do this no matter what software you
run -- it is a network card and DMX is not network traffic. Check first:

    macOS:  ls /dev/tty.*            before and after plugging it in
            system_profiler SPUSBDataType | grep -i -A4 'product id'
    Linux:  ls /dev/ttyUSB* /dev/ttyACM*   and   dmesg | tail

A new /dev/tty.usbserial* or /dev/ttyUSB* means SERIAL -> this script may
work. A new network interface (en5, eth1) means ETHERNET -> it cannot.

HOW DMX FRAMING WORKS, AND THE CAVEAT

DMX512 is 250000 baud, 8 data bits, 2 stop bits, no parity. Each packet
begins with a BREAK (the line held low ~88us, which is longer than any legal
character), then a mark, then a start code byte (0x00 for standard dimmer
data), then up to 512 channel bytes.

A generic UART cannot see a break directly -- it surfaces as a framing error
or as a spurious 0x00. This script therefore frames on the IDLE GAP between
packets, which is reliable in practice because DMX refreshes ~44x/second and
the inter-packet gap is far longer than the ~44us it takes to send one byte
at 250k. It is not bulletproof; a dedicated DMX interface (Enttec) is if you
need certainty.

Requires pyserial:  pip install pyserial
"""

import argparse, csv, sys, time


BAUD = 250000
GAP_S = 0.001          # idle longer than this ends a packet (1 ms >> 44 us)


def frame_bytes(chunks, gap_s=GAP_S):
    """Turn (timestamp, bytes) chunks into DMX packets by idle-gap framing.

    Pure and side-effect free so the framing logic can be tested without
    hardware -- see --selftest.
    Yields (t_start, start_code, [channel values]).
    """
    buf, t0, last = bytearray(), None, None
    for t, data in chunks:
        if last is not None and (t - last) > gap_s and buf:
            yield _emit(t0, buf)
            buf, t0 = bytearray(), None
        if not buf:
            t0 = t
        buf += data
        last = t
    if buf:
        yield _emit(t0, buf)


def _emit(t0, buf):
    return (t0, buf[0] if buf else None, list(buf[1:513]))


def selftest():
    """Feed synthetic chunks through the framer and check it recovers
    packets. Two packets separated by an idle gap, one split across reads."""
    packets = [bytes([0x00, 10, 20, 30, 40]), bytes([0x00, 11, 21, 31, 41])]
    chunks = [
        (0.000, packets[0][:3]),
        (0.0002, packets[0][3:]),        # same packet, split read
        (0.0230, packets[1]),            # after a gap -> new packet
    ]
    got = list(frame_bytes(chunks))
    assert len(got) == 2, f"expected 2 packets, got {len(got)}"
    assert got[0][1] == 0 and got[1][1] == 0, "start code should be 0x00"
    assert got[0][2] == [10, 20, 30, 40], got[0][2]
    assert got[1][2] == [11, 21, 31, 41], got[1][2]
    # a 512-channel packet should not overflow
    big = [(0.0, bytes([0]) + bytes(range(256)) * 3)]
    assert len(list(frame_bytes(big))[0][2]) == 512
    print("framing self-test passed: split reads joined, gap split packets, "
          "512-channel cap held")


def list_ports():
    try:
        from serial.tools import list_ports
    except ImportError:
        print("pyserial not installed:  pip install pyserial")
        return
    ports = list(list_ports.comports())
    if not ports:
        print("no serial ports found.")
        print("If you plugged in a dongle and nothing appeared, it is "
              "probably a\nUSB-to-ETHERNET adapter, not serial. Check for a "
              "new network\ninterface instead (macOS: networksetup "
              "-listallhardwareports).")
        return
    for p in ports:
        print(f"  {p.device}")
        print(f"      {p.description}")
        if p.vid is not None:
            print(f"      vid:pid {p.vid:04x}:{p.pid:04x}")
    print("\nFTDI / CH340 / CP210x / PL2303 in the description means it is a "
          "serial\nadapter. Whether it is RS-485 or plain RS-232 depends on "
          "the dongle;\nDMX needs RS-485.")


def capture(port, out_path, seconds, quiet):
    try:
        import serial
    except ImportError:
        raise SystemExit("pyserial not installed:  pip install pyserial")

    ser = serial.Serial(port, BAUD, bytesize=8, parity="N", stopbits=2,
                        timeout=0.005)
    print(f"listening on {port} at {BAUD} 8N2 -- Ctrl-C to stop")

    def reads():
        t_end = time.time() + seconds if seconds else None
        while t_end is None or time.time() < t_end:
            n = ser.in_waiting
            data = ser.read(n if n else 1)
            if data:
                yield (time.time(), data)
            else:
                yield (time.time(), b"")

    def nonempty(gen):
        for t, d in gen:
            if d:
                yield (t, d)

    n = 0
    t0 = None
    with open(out_path, "w", newline="") as fh:
        w = csv.writer(fh)
        try:
            for t, sc, vals in frame_bytes(nonempty(reads())):
                if not vals:
                    continue
                if sc not in (0x00, None) and n == 0:
                    print(f"  note: start code 0x{sc:02X}, not 0x00 -- this "
                          f"may not be standard dimmer data")
                if t0 is None:
                    t0 = t
                w.writerow([round(t - t0, 5)] + vals)
                n += 1
                if not quiet and n % 44 == 0:
                    active = sum(1 for v in vals if v)
                    print(f"\r  {n} packets, {len(vals)} channels, "
                          f"{active} non-zero  ", end="", flush=True)
        except KeyboardInterrupt:
            pass
    ser.close()
    print(f"\nwrote {n} packets to {out_path}")
    if n == 0:
        print("Nothing received. Either the adapter is not RS-485, the A/B "
              "lines are\nswapped (try swapping them -- harmless), the pinout "
              "differs, or the\nport is not sending DMX at all.")
    else:
        print(f"Now run:  python tools/dmx_diff.py {out_path} "
              f"--events <times you saw scenes change>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port", nargs="?")
    ap.add_argument("out", nargs="?", default="out/capture.csv")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--seconds", type=float, default=0)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.list or not a.port:
        return list_ports()
    import os
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    capture(a.port, a.out, a.seconds, a.quiet)


if __name__ == "__main__":
    main()
