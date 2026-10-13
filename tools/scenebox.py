#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyserial>=3.5",
#     "textual>=0.70",
# ]
# ///
"""
scenebox.py -- a TUI for picking scenes on a GC-6004 over USB->DMX.

    uv run scenebox.py
    uv run scenebox.py --addr 14

uv reads the dependency block at the top of this file and builds the
environment itself, so there is nothing to pip install and nothing to
activate.  First run takes a few seconds; after that it is instant.

What it sends, from the controller's base address:

    ch +0   brightness     (adjustable, default 255)
    ch +1   red adjust     same
    ch +2   green adjust   same
    ch +3   blue adjust    same
    ch +4   white adjust   same
    ch +5   SCENE          (n-1)*4 + 1
    ch +6   speed          ONLY when you turn it on with `s`

Nothing above the scene channel is written unless you ask for it.  DMX
cannot send a partial frame -- the floor is 24 slots -- so channels past
the ones we set do go out, as zero.  Channel +6 is speed and 0 is the
SLOWEST setting, so with speed off the show plays slow.  That is the
honest cost of "touch nothing past the scene channel".  Press `s` for
native rate.

Keys
----
  1-9 0       type a scene number, Enter to go, Esc to clear
  < >         previous / next scene       (also , and .)
  s           speed channel off / 255
  b           blackout toggle
  + -         brightness up / down by 16
  r           re-send the current scene (restarts the file from frame 0)
  q           quit

Quit the ENTTEC software first -- it holds the serial port open.
"""

import argparse
import glob
import sys
import threading
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial missing. Run this with:  uv run scenebox.py")

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Button, Footer, Static

START, END = 0x7E, 0xE7
LBL_PARAMS_REQ = 3
LBL_DMX = 6
MIN_SLOTS = 24                 # DMX512 floor; we cannot send fewer
MAX_SCENE = 62                 # the GC-6004 holds 62 program files


def scene_value(n):
    """Scene n -> value on the scene channel. Four DMX values per scene."""
    return (n - 1) * 4 + 1


# ----------------------------------------------------------------- discovery
def find_ports():
    pats = ("/dev/cu.usbserial*", "/dev/cu.usbmodem*", "/dev/tty.usbserial*",
            "/dev/ttyUSB*", "/dev/ttyACM*", "COM*")
    out = []
    for p in pats:
        out.extend(sorted(glob.glob(p)))
    # macOS exposes every device twice: /dev/cu.X (what you want) and /dev/tty.X
    cu = {p.rsplit("/", 1)[-1][3:] for p in out if p.startswith("/dev/cu.")}
    return [p for p in out
            if not (p.startswith("/dev/tty.") and p.rsplit("/", 1)[-1][4:] in cu)]


def pro_msg(label, data=b""):
    n = len(data)
    return bytes([START, label, n & 0xFF, (n >> 8) & 0xFF]) + bytes(data) + bytes([END])


def is_pro(ser):
    ser.reset_input_buffer()
    ser.write(pro_msg(LBL_PARAMS_REQ, b"\x00\x00"))
    ser.flush()
    t0, buf = time.time(), bytearray()
    while time.time() - t0 < 0.6:
        chunk = ser.read(64)
        if chunk:
            buf += chunk
            if buf.find(bytes([START])) >= 0 and len(buf) > 8:
                return True
        else:
            time.sleep(0.01)
    return False


# -------------------------------------------------------------- DMX engine
class DmxEngine:
    """Holds a universe and re-asserts it on a background thread.

    The controllers need the value repeated, not sent once. A dropped frame
    is harmless; a stopped thread is not, so write errors are counted and
    surfaced rather than raised.
    """

    def __init__(self, port=None, slots=MIN_SLOTS, hz=40):
        ports = find_ports()
        if port is None:
            if not ports:
                sys.exit("No USB serial device found.\n"
                         "  - is the ENTTEC plugged in?\n"
                         "  - is the ENTTEC software still running? quit it.\n"
                         "  - try:  ls /dev/cu.*")
            port = ports[0]
        self.port = port
        self.slots = max(MIN_SLOTS, min(512, slots))
        self.data = bytearray(512)
        self.hz = hz
        self.errors = 0
        self.frames = 0
        self.lock = threading.Lock()
        self._stop = threading.Event()

        probe = serial.Serial(port, baudrate=115200, timeout=0.2)
        self.kind = "pro" if is_pro(probe) else "open"
        probe.close()
        if self.kind == "pro":
            self.ser = serial.Serial(port, baudrate=115200, timeout=0.2)
        else:
            self.ser = serial.Serial(port, baudrate=250000, bytesize=8,
                                     stopbits=serial.STOPBITS_TWO,
                                     parity=serial.PARITY_NONE, timeout=0.2)
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def set_slots(self, n):
        with self.lock:
            self.slots = max(MIN_SLOTS, min(512, n))

    def __setitem__(self, ch, val):
        if not 1 <= ch <= 512:
            raise ValueError(f"channel {ch} out of range")
        with self.lock:
            self.data[ch - 1] = max(0, min(255, int(val)))

    def __getitem__(self, ch):
        with self.lock:
            return self.data[ch - 1]

    def _pump(self):
        period = 1.0 / max(1, self.hz)
        nxt = time.monotonic()
        while not self._stop.is_set():
            try:
                with self.lock:
                    payload = bytes(self.data[:self.slots])
                if self.kind == "pro":
                    self.ser.write(pro_msg(LBL_DMX, b"\x00" + payload))
                else:
                    self.ser.break_condition = True
                    time.sleep(0.00012)
                    self.ser.break_condition = False
                    time.sleep(0.00002)
                    self.ser.write(b"\x00" + payload)
                self.ser.flush()
                self.frames += 1
            except Exception:
                self.errors += 1
                time.sleep(0.2)
            nxt += period
            time.sleep(max(0, nxt - time.monotonic()))

    def stop(self):
        self._stop.set()
        self.thread.join(timeout=1.0)
        try:
            self.ser.close()
        except Exception:
            pass


# -------------------------------------------------------------------- TUI
class SceneBox(App):
    CSS = """
    Screen { layout: vertical; }
    #status {
        height: 4; padding: 0 1; background: $panel; color: $text;
        border-bottom: solid $primary;
    }
    #wire { height: 3; padding: 0 1; color: $text-muted; }
    #grid { height: 1fr; }
    #grid Button {
        width: 10; min-width: 10; height: 3; margin: 0;
    }
    .row { height: auto; }
    """

    BINDINGS = [
        ("q", "quit", "quit"),
        ("s", "toggle_speed", "speed"),
        ("b", "toggle_black", "blackout"),
        ("r", "restart", "re-fire"),
        ("plus,equals_sign", "bright_up", "bright+"),
        ("minus", "bright_down", "bright-"),
        ("comma,less_than_sign", "prev", "prev"),
        ("period,greater_than_sign", "next", "next"),
    ]

    scene = reactive(1)
    level = reactive(255)
    speed_on = reactive(False)
    black = reactive(False)

    def __init__(self, dmx, addr):
        super().__init__()
        self.dmx = dmx
        self.addr = addr
        self.typed = ""

    # ------------------------------------------------------------- layout
    def compose(self) -> ComposeResult:
        yield Static("", id="status")
        yield Static("", id="wire")
        with VerticalScroll(id="grid"):
            row = []
            for n in range(1, MAX_SCENE + 1):
                row.append(Button(f"{n}", id=f"sc{n}"))
                if len(row) == 8:
                    yield Horizontal(*row, classes="row")
                    row = []
            if row:
                yield Horizontal(*row, classes="row")
        yield Footer()

    def on_mount(self):
        self.apply()
        self.set_interval(0.5, self.refresh_status)

    # -------------------------------------------------------------- output
    def apply(self):
        """Write the whole block. Called on every change."""
        a = self.addr
        lvl = 0 if self.black else self.level
        self.dmx[a + 0] = lvl
        self.dmx[a + 1] = lvl
        self.dmx[a + 2] = lvl
        self.dmx[a + 3] = lvl
        self.dmx[a + 4] = lvl
        self.dmx[a + 5] = scene_value(self.scene)
        if self.speed_on:
            self.dmx[a + 6] = 255
            self.dmx.set_slots(max(MIN_SLOTS, a + 6))
        else:
            self.dmx[a + 6] = 0
            self.dmx.set_slots(max(MIN_SLOTS, a + 5))
        self.refresh_status()
        self.mark_buttons()

    def mark_buttons(self):
        for n in range(1, MAX_SCENE + 1):
            try:
                b = self.query_one(f"#sc{n}", Button)
            except Exception:
                continue
            b.variant = "success" if n == self.scene else "default"

    def refresh_status(self):
        a = self.addr
        val = scene_value(self.scene)
        typed = f"  typing: {self.typed}" if self.typed else ""
        err = f"   errors {self.dmx.errors}" if self.dmx.errors else ""
        self.query_one("#status", Static).update(
            f"[b]SCENE {self.scene}[/b]   value {val}   base addr {a}\n"
            f"{self.dmx.port}  {'DMX USB PRO' if self.dmx.kind == 'pro' else 'Open DMX USB'}"
            f"   {self.dmx.slots} slots @ {self.dmx.hz} Hz{err}{typed}"
        )
        lvl = 0 if self.black else self.level
        speed = "255 (native)" if self.speed_on else "0 — NOT WRITTEN, plays slow"
        self.query_one("#wire", Static).update(
            f"ch {a}-{a+4} = {lvl}   ch {a+5} = {val}   ch {a+6} speed = {speed}"
            + ("   [b]BLACKOUT[/b]" if self.black else "")
        )

    # ------------------------------------------------------------ actions
    def go(self, n):
        if 1 <= n <= MAX_SCENE:
            self.scene = n
            self.apply()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id and event.button.id.startswith("sc"):
            self.go(int(event.button.id[2:]))

    def on_key(self, event):
        k = event.key
        if k.isdigit():
            self.typed += k
            if int(self.typed or "0") > MAX_SCENE:
                self.typed = k
            self.refresh_status()
        elif k == "enter" and self.typed:
            self.go(int(self.typed))
            self.typed = ""
        elif k == "escape":
            self.typed = ""
            self.refresh_status()
        elif k == "backspace":
            self.typed = self.typed[:-1]
            self.refresh_status()

    def action_prev(self):
        self.go(self.scene - 1 if self.scene > 1 else MAX_SCENE)

    def action_next(self):
        self.go(self.scene + 1 if self.scene < MAX_SCENE else 1)

    def action_toggle_speed(self):
        self.speed_on = not self.speed_on
        self.apply()

    def action_toggle_black(self):
        self.black = not self.black
        self.apply()

    def action_bright_up(self):
        self.level = min(255, self.level + 16)
        self.black = False
        self.apply()

    def action_bright_down(self):
        self.level = max(0, self.level - 16)
        self.apply()

    def action_restart(self):
        """Re-fire the scene. Bouncing the value restarts the file at frame 0."""
        a = self.addr
        self.dmx[a + 5] = 0
        time.sleep(0.1)
        self.dmx[a + 5] = scene_value(self.scene)

    def action_quit(self):
        self.dmx.stop()
        self.exit()


def main():
    ap = argparse.ArgumentParser(description="TUI scene selector for the GC-6004.")
    ap.add_argument("--addr", type=int, default=1, help="base address (default 1)")
    ap.add_argument("--scene", type=int, default=1, help="scene to start on")
    ap.add_argument("--speed", action="store_true",
                    help="start with the speed channel at 255")
    ap.add_argument("--hz", type=int, default=40)
    ap.add_argument("--port", default=None)
    args = ap.parse_args()

    dmx = DmxEngine(port=args.port, slots=max(MIN_SLOTS, args.addr + 6), hz=args.hz)
    app = SceneBox(dmx, args.addr)
    app.scene = max(1, min(MAX_SCENE, args.scene))
    app.speed_on = args.speed
    try:
        app.run()
    finally:
        dmx.stop()


if __name__ == "__main__":
    main()
