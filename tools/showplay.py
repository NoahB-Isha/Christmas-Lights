#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyserial>=3.5",
#     "miniaudio>=1.60",
# ]
# ///
"""
showplay.py -- play the music and fire the matching scenes over DMX from ONE clock, with a UI in
your browser.

    cd ~/Documents/Lightshow/repo
    uv run tools/showplay.py                    # the whole show: assets/audio/show16.mp3 + one scene per song
    uv run tools/showplay.py --scene 1          # ONE scene for the whole file (the single-file show as Sc-01)
    uv run tools/showplay.py --from 3           # start at song/scene 3
    uv run tools/showplay.py --no-dmx           # rehearse without the ENTTEC
    uv run tools/showplay.py --audio idle.mp3 --scene 4

It opens http://127.0.0.1:8777 in your browser (the terminal window must stay open).

Files it looks for (override with --cues / --audio):
    an .mp3 next to this script, else assets/audio/show16.mp3
    cues.json next to this script, else out/studio/cards/cues.json   (Render & cards -> "One scene per song")
    out/showplay.json  saved settings (lead ms, brightness);  out/showplay.log  when each scene fired

THE ONE NUMBER THAT MATTERS: lead (ms). The controller takes a moment between receiving a scene
select and the first frame lighting up, and the audio device has its own latency. `lead` is how much
earlier than the audio the DMX cue goes out. Positive = DMX first. Slider / buttons in the UI; saved.

DMX block, from the base address (same as scenebox.py):
    +0 brightness  +1..+4 R/G/B/W adjust (all = brightness -- at 0 they MUTE the output)
    +5 SCENE  value (n-1)*4+1      +6 speed 255 (native)

Quit the ENTTEC software first -- it holds the serial port open.
"""

import argparse
import array
import glob
import json
import os
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import serial
except ImportError:
    sys.exit("pyserial missing. Run this with:  uv run showplay.py")
try:
    import miniaudio
except ImportError:
    sys.exit("miniaudio missing. Run this with:  uv run showplay.py")

HERE = os.path.dirname(os.path.abspath(__file__))          # this script lives next to the music
REPO = os.path.join(HERE, "repo")                            # ~/Documents/Lightshow/repo  (script beside the music)
if not os.path.isdir(REPO) and os.path.isdir(os.path.join(os.path.dirname(HERE), "src", "lightshow")):
    REPO = os.path.dirname(HERE)                              # the copy in repo/tools/
START, END = 0x7E, 0xE7
LBL_PARAMS_REQ, LBL_DMX = 3, 6
MIN_SLOTS = 24
MAX_SCENE = 62
_STATE_DIR = os.path.join(REPO, "out") if os.path.isdir(REPO) else HERE
os.makedirs(_STATE_DIR, exist_ok=True)
SETTINGS = os.path.join(_STATE_DIR, "showplay.json")          # saved lead / brightness (out/ is git-ignored)
LOG = os.path.join(_STATE_DIR, "showplay.log")


def default_audio():
    files = sorted(glob.glob(os.path.join(HERE, "*.mp3")) + glob.glob(os.path.join(HERE, "*.m4a")) + glob.glob(os.path.join(HERE, "*.wav")))
    return files[0] if files else os.path.join(REPO, "assets", "audio", "show16.mp3")


def default_cues():
    for c in (os.path.join(HERE, "cues.json"), os.path.join(REPO, "out", "studio", "cards", "cues.json")):
        if os.path.exists(c):
            return c
    return os.path.join(REPO, "out", "studio", "cards", "cues.json")


def scene_value(n):
    return (n - 1) * 4 + 1


# ----------------------------------------------------------------- DMX (as in scenebox.py)
def find_ports():
    pats = ("/dev/cu.usbserial*", "/dev/cu.usbmodem*", "/dev/tty.usbserial*", "/dev/ttyUSB*", "/dev/ttyACM*", "COM*")
    out = []
    for p in pats:
        out.extend(sorted(glob.glob(p)))
    cu = {p.rsplit("/", 1)[-1][3:] for p in out if p.startswith("/dev/cu.")}
    return [p for p in out if not (p.startswith("/dev/tty.") and p.rsplit("/", 1)[-1][4:] in cu)]


def pro_msg(label, data=b""):
    n = len(data)
    return bytes([START, label, n & 0xFF, (n >> 8) & 0xFF]) + bytes(data) + bytes([END])


def is_pro(ser):
    ser.reset_input_buffer()
    ser.write(pro_msg(LBL_PARAMS_REQ, b"\x00\x00")); ser.flush()
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


class DmxEngine:
    """Holds a universe and re-asserts it at `hz` on a background thread (the controllers need
    the value repeated, not sent once). Write errors are counted, never raised."""

    def __init__(self, port=None, slots=MIN_SLOTS, hz=40):
        ports = find_ports()
        if port is None:
            if not ports:
                sys.exit("No USB serial device found (ENTTEC plugged in? ENTTEC software quit?). Try --no-dmx to rehearse.")
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
        self.kind = "DMX USB Pro" if is_pro(probe) else "Open DMX USB"
        probe.close()
        if self.kind == "DMX USB Pro":
            self.ser = serial.Serial(port, baudrate=115200, timeout=0.2)
        else:
            self.ser = serial.Serial(port, baudrate=250000, bytesize=8, stopbits=serial.STOPBITS_TWO,
                                     parity=serial.PARITY_NONE, timeout=0.2)
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def __setitem__(self, ch, val):
        with self.lock:
            self.data[ch - 1] = max(0, min(255, int(val)))

    def send_now(self):
        """Push the current universe immediately (a cue must not wait for the next 25 ms tick)."""
        with self.lock:
            payload = bytes(self.data[:self.slots])
        try:
            self._write(payload)
        except Exception:
            self.errors += 1

    def _write(self, payload):
        if self.kind == "DMX USB Pro":
            self.ser.write(pro_msg(LBL_DMX, b"\x00" + payload))
        else:
            self.ser.break_condition = True; time.sleep(0.00012)
            self.ser.break_condition = False; time.sleep(0.00002)
            self.ser.write(b"\x00" + payload)
        self.ser.flush()
        self.frames += 1

    def _pump(self):
        period = 1.0 / max(1, self.hz)
        nxt = time.monotonic()
        while not self._stop.is_set():
            try:
                with self.lock:
                    payload = bytes(self.data[:self.slots])
                self._write(payload)
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


class NullDmx:
    """--no-dmx: same interface, writes nothing (rehearse the timing with audio only)."""
    port, kind, errors, frames, slots, hz = "none", "no DMX (rehearsal)", 0, 0, 0, 0

    def __setitem__(self, ch, val): pass
    def send_now(self): pass
    def stop(self): pass


# ----------------------------------------------------------------- audio clock
class AudioClock:
    """Decodes the whole track once, plays it through miniaudio, and reports the position of the
    sample currently being handed to the device. The show runs off THIS clock: wall time is never
    trusted. `pos()` = seconds into the file; seek() jumps."""

    def __init__(self, path, buffer_ms=100):
        snd = miniaudio.decode_file(path, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=2, sample_rate=44100)
        self.rate, self.nch = snd.sample_rate, snd.nchannels
        self.samples = snd.samples                                  # array('h'), interleaved
        self.nframes = len(self.samples) // self.nch
        self.duration = self.nframes / self.rate
        self.frame = 0                                              # next frame to deliver
        self.playing = False
        self.lock = threading.Lock()
        self.device = miniaudio.PlaybackDevice(output_format=miniaudio.SampleFormat.SIGNED16, nchannels=self.nch,
                                               sample_rate=self.rate, buffersize_msec=buffer_ms)
        self.latency_s = buffer_ms / 1000.0                         # what the device holds ahead of the speaker
        gen = self._gen(); next(gen)
        self.device.start(gen)

    def _gen(self):
        want = yield b""
        silence = array.array("h")
        while True:
            if len(silence) < want * self.nch:
                silence = array.array("h", bytes(2 * want * self.nch))
            with self.lock:
                if self.playing and self.frame < self.nframes:
                    a, b = self.frame * self.nch, min(self.nframes, self.frame + want) * self.nch
                    chunk = self.samples[a:b]
                    self.frame += want
                    if len(chunk) < want * self.nch:                # ran off the end: pad, stop
                        chunk = chunk + silence[:want * self.nch - len(chunk)]
                        self.playing = False
                else:
                    chunk = silence[:want * self.nch]
            want = yield chunk

    def pos(self):
        with self.lock:
            return max(0.0, self.frame / self.rate - self.latency_s)

    def seek(self, t):
        with self.lock:
            self.frame = int(max(0.0, min(self.duration, t)) * self.rate)

    def play(self, on=True):
        with self.lock:
            self.playing = on

    def stop(self):
        try:
            self.device.close()
        except Exception:
            pass


# ----------------------------------------------------------------- settings
def load_settings():
    try:
        return json.load(open(SETTINGS))
    except Exception:
        return {}


def save_settings(**kw):
    d = load_settings(); d.update(kw)
    json.dump(d, open(SETTINGS, "w"), indent=1)


# ----------------------------------------------------------------- the player
class Player:
    """The show: audio clock + cue list + DMX. All commands come through `cmd()`; the 5 ms tick
    decides cue timing. Thread-safe enough for one browser tab."""

    def __init__(self, dmx, audio, cues, addr, lead_ms, level=255, audio_name=""):
        self.dmx, self.audio, self.cues, self.addr = dmx, audio, cues, addr
        self.lead_ms = int(lead_ms)
        self.level, self.black = int(level), False
        self.cur = -1
        self.manual_scene = None                                    # a scene fired by hand (idle etc.)
        self.fired_at = {}
        self.log = []
        self.audio_name = audio_name
        self.lock = threading.RLock()
        self._stop = threading.Event()
        self.write_block()
        threading.Thread(target=self._ticker, daemon=True).start()

    # ---- DMX
    def write_block(self):
        a = self.addr
        lvl = 0 if self.black else self.level
        for k in range(5):
            self.dmx[a + k] = lvl
        self.dmx[a + 6] = 255

    def _fire_scene(self, scene):
        self.dmx[self.addr + 5] = scene_value(scene)
        self.dmx.send_now()

    def fire(self, i):
        c = self.cues[i]
        self._fire_scene(c["scene"])
        self.cur = i
        self.manual_scene = None
        self.fired_at[i] = round(self.audio.pos(), 3)
        self.log.append({"t": time.strftime("%H:%M:%S"), "scene": c["scene"], "audio": self.fired_at[i], "lead": self.lead_ms, "name": c["name"]})
        self.log = self.log[-200:]

    def refire(self, scene):
        """Bounce the scene value so the controller restarts the file at frame 0."""
        self.dmx[self.addr + 5] = 0
        self.dmx.send_now()
        time.sleep(0.06)
        self._fire_scene(scene)

    # ---- transport
    def jump(self, i):
        """Go to cue i: audio to its t0, scene fired `lead` early (we wait, not the audio)."""
        with self.lock:
            i = max(0, min(len(self.cues) - 1, i))
            self.audio.play(False)
            self.audio.seek(self.cues[i]["t0"])
            if self.cur == i:
                self.refire(self.cues[i]["scene"]); self.manual_scene = None
                self.fired_at[i] = round(self.audio.pos(), 3)
                self.log.append({"t": time.strftime("%H:%M:%S"), "scene": self.cues[i]["scene"], "audio": self.fired_at[i], "lead": self.lead_ms, "name": "re-fire " + self.cues[i]["name"]})
            else:
                self.fire(i)
            time.sleep(max(0.0, self.lead_ms / 1000.0))
            self.audio.play(True)

    def _ticker(self):
        while not self._stop.is_set():
            try:
                if self.audio.playing and self.manual_scene is None:
                    pos = self.audio.pos()
                    nxt = self.cur + 1
                    if nxt < len(self.cues) and pos >= self.cues[nxt]["t0"] - self.lead_ms / 1000.0:
                        with self.lock:
                            self.fire(nxt)
            except Exception:
                pass
            time.sleep(0.005)

    # ---- commands from the UI
    def cmd(self, op, **kw):
        with self.lock:
            if op == "toggle":
                self.audio.play(not self.audio.playing)
            elif op == "play":
                self.audio.play(True)
            elif op == "pause":
                self.audio.play(False)
            elif op == "next":
                self.jump(self.cur + 1)
            elif op == "prev":
                self.jump(self.cur - 1)
            elif op == "goto":
                self.jump(int(kw["index"]))
            elif op == "refire":
                self.jump(max(0, self.cur))
            elif op == "seek":                                      # drag the progress bar: audio only; scene follows at the next cue
                t = float(kw["t"]); self.audio.seek(t)
                self.cur = max([i for i, c in enumerate(self.cues) if c["t0"] <= t + self.lead_ms / 1000.0] or [-1])
                if self.cur >= 0 and self.manual_scene is None:
                    self.refire(self.cues[self.cur]["scene"])
            elif op == "lead":
                self.lead_ms = int(max(-2000, min(2000, int(kw["ms"])))); save_settings(lead_ms=self.lead_ms)
            elif op == "level":
                self.level = int(max(0, min(255, int(kw["level"])))); self.black = False; self.write_block(); save_settings(level=self.level)
            elif op == "black":
                self.black = not self.black; self.write_block()
            elif op == "scene":                                     # fire any scene by hand (idle patterns, tests)
                n = int(kw["n"])
                if 1 <= n <= MAX_SCENE:
                    self.audio.play(False); self.manual_scene = n; self.refire(n)
                    self.log.append({"t": time.strftime("%H:%M:%S"), "scene": n, "audio": round(self.audio.pos(), 3), "lead": self.lead_ms, "name": "manual"})
            elif op == "stop":
                self.audio.play(False)
            return self.state()

    def state(self):
        pos = self.audio.pos()
        return {"playing": self.audio.playing, "pos": round(pos, 3), "duration": round(self.audio.duration, 2),
                "cur": self.cur, "manual_scene": self.manual_scene, "lead_ms": self.lead_ms, "level": self.level, "black": self.black,
                "cues": [{**c, "fired_at": self.fired_at.get(i)} for i, c in enumerate(self.cues)],
                "dmx": {"port": self.dmx.port, "kind": self.dmx.kind, "errors": self.dmx.errors, "addr": self.addr},
                "audio_name": self.audio_name, "log": self.log[-12:][::-1]}

    def shutdown(self):
        self._stop.set()
        try:
            with open(LOG, "a") as fh:
                for r in self.log:
                    fh.write(f"{r['t']}  scene {r['scene']:2d}  audio {r['audio']:8.3f}s  lead {r['lead']:+d} ms  {r['name']}\n")
        except Exception:
            pass
        self.audio.stop(); self.dmx.stop()


# ----------------------------------------------------------------- the web UI
PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Show player</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0f1115;--panel:#181b22;--line:#2a2f3a;--txt:#e8ebf2;--dim:#8d94a6;--acc:#4da3ff;--ok:#39c46b;--warn:#ffb020;--bad:#ff4d4d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.4 -apple-system,system-ui,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:16px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:14px}
h1{font-size:18px;margin:0 0 6px}h2{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--dim);margin:0 0 10px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
button{background:#232833;color:var(--txt);border:1px solid var(--line);border-radius:10px;padding:10px 16px;font-size:15px;cursor:pointer}
button:hover{border-color:var(--acc)}button.big{font-size:20px;padding:14px 26px;min-width:120px}
button.primary{background:var(--acc);color:#061018;border-color:var(--acc);font-weight:700}
button.danger{background:#3a1a1a;border-color:#6a2a2a}button.on{outline:2px solid var(--ok)}
.time{font:600 34px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.02em}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.bar{position:relative;height:34px;background:#0b0d12;border:1px solid var(--line);border-radius:8px;overflow:hidden;cursor:pointer;margin:10px 0}
.seg{position:absolute;top:0;bottom:0;border-right:1px solid #2f3540;background:#1b2130;font-size:11px;color:var(--dim);padding:2px 6px;overflow:hidden;white-space:nowrap}
.seg.cur{background:#1f3b5c;color:#fff}.seg.done{background:#15202c}
.head{position:absolute;top:0;bottom:0;width:2px;z-index:2;background:var(--acc);box-shadow:0 0 8px var(--acc)}
.cues{width:100%;border-collapse:collapse}.cues td,.cues th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;font-size:14px}
.cues tr.cur td{background:#1f3b5c}.cues tr{cursor:pointer}.cues tr:hover td{background:#222a38}.cues th{color:var(--dim);font-weight:500}
input[type=range]{width:260px}input[type=number]{width:90px;background:#0b0d12;color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:8px;font-size:16px}
.lead{font:700 26px/1 ui-monospace,Menlo,monospace;min-width:120px;text-align:center}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(46px,1fr));gap:6px}.grid button{padding:8px 0;font-size:13px}
.grid button.cur{background:#1f3b5c;border-color:var(--acc)}
.dim{color:var(--dim)}.ok{color:var(--ok)}.bad{color:var(--bad)}.log{font-size:12.5px;max-height:160px;overflow:auto}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;background:#232833;font-size:12px;color:var(--dim)}
.kbd{font:12px ui-monospace,Menlo,monospace;background:#232833;border:1px solid var(--line);border-radius:4px;padding:1px 5px;color:var(--dim)}
</style></head><body><div class="wrap">
<div class="panel"><div class="row" style="justify-content:space-between"><div><h1 id="title">Show player</h1><div class="dim" id="dmxline"></div></div>
<div class="row"><div class="time" id="time">0:00.00</div><span class="pill" id="playstate">paused</span></div></div>
<div class="bar" id="bar"><div class="head" id="head"></div></div>
<div class="row">
<button id="bPrev" title="previous song (p)">⏮ Prev</button>
<button id="bPlay" class="big primary" title="play / pause (space)">▶ Play</button>
<button id="bNext" title="next song (n)">Next ⏭</button>
<button id="bRefire" title="re-fire the current scene and restart the audio at its cue (r)">↻ Re-sync</button>
<span style="flex:1"></span>
<button id="bBlack" class="danger" title="blackout (b)">Blackout</button>
</div></div>

<div class="panel"><h2>Lead — DMX goes out this much before the audio cue</h2>
<div class="row">
<button id="l_m50">−50</button><button id="l_m10">−10</button>
<div class="lead" id="leadv">+0 ms</div>
<button id="l_p10">+10</button><button id="l_p50">+50</button>
<input type="range" id="leadr" min="-1000" max="1000" step="10">
<input type="number" id="leadn" step="10"> <span class="dim">ms</span>
<span class="dim" style="flex-basis:100%">Positive = DMX first. Lights late → raise it; lights early → lower it. Saved automatically. Keys: <span class="kbd">[</span> <span class="kbd">]</span> ±10, <span class="kbd">{</span> <span class="kbd">}</span> ±50.</span>
</div></div>

<div class="panel"><div class="row" style="gap:28px">
<div><h2>Brightness</h2><div class="row"><input type="range" id="level" min="0" max="255"><span class="mono" id="levelv">255</span></div></div>
<div style="flex:1"><h2>Cues (click a song to jump to it)</h2><table class="cues" id="cues"></table></div>
</div></div>

<div class="panel"><h2>Fire any scene by hand (idle patterns, test cards) — stops the audio</h2><div class="grid" id="scenes"></div></div>
<div class="panel"><h2>Log</h2><div class="log mono" id="log"></div></div>
</div>
<script>
const $=s=>document.querySelector(s); let S=null, dragging=false;
async function cmd(op,extra){const r=await fetch('/cmd',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({op,...extra})});S=await r.json();draw(true);}
async function poll(){try{const r=await fetch('/state');S=await r.json();draw(false);}catch(e){$('#playstate').textContent='no connection — is the terminal still running?';}}
function fmt(t){const m=Math.floor(t/60),s=(t-m*60).toFixed(2).padStart(5,'0');return `${m}:${s}`;}
function draw(full){
  if(!S)return;
  $('#time').textContent=fmt(S.pos);
  $('#playstate').textContent=S.manual_scene?`manual scene ${S.manual_scene}`:(S.playing?'PLAYING':'paused');
  $('#playstate').style.color=S.playing?'var(--ok)':'var(--dim)';
  $('#bPlay').textContent=S.playing?'⏸ Pause':'▶ Play';
  $('#title').textContent=S.audio_name||'Show player';
  $('#dmxline').innerHTML=`${S.dmx.kind} · ${S.dmx.port} · base addr ${S.dmx.addr}`+(S.dmx.errors?` · <span class="bad">${S.dmx.errors} DMX write errors</span>`:'')+(S.black?' · <b class="bad">BLACKOUT</b>':'');
  $('#bBlack').classList.toggle('on',S.black);
  if(document.activeElement!==$('#leadn')){$('#leadv').textContent=(S.lead_ms>=0?'+':'')+S.lead_ms+' ms';$('#leadr').value=S.lead_ms;$('#leadn').value=S.lead_ms;}
  if(document.activeElement!==$('#level')){$('#level').value=S.level;$('#levelv').textContent=S.level;}
  const bar=$('#bar'); const D=S.duration||1;
  if(full||bar.childElementCount<2){bar.innerHTML='<div class="head" id="head"></div>';S.cues.forEach((c,i)=>{const d=document.createElement('div');d.className='seg';d.style.left=(100*c.t0/D)+'%';d.style.width=(100*(Math.min(c.t1,D)-c.t0)/D)+'%';d.textContent=`Sc-${String(c.scene).padStart(2,'0')} ${c.name}`;d.title=c.name;d.dataset.i=i;bar.appendChild(d);});}
  [...bar.querySelectorAll('.seg')].forEach(d=>{const i=+d.dataset.i;d.classList.toggle('cur',i===S.cur&&!S.manual_scene);d.classList.toggle('done',i<S.cur);});
  $('#head').style.left=(100*S.pos/D)+'%';
  const tb=$('#cues'); tb.innerHTML='<tr><th>scene</th><th>DMX</th><th>song</th><th>cue</th><th>fired at</th></tr>'+S.cues.map((c,i)=>`<tr class="${i===S.cur&&!S.manual_scene?'cur':''}" data-i="${i}"><td class="mono">Sc-${String(c.scene).padStart(2,'0')}</td><td class="mono">${(c.scene-1)*4+1}</td><td>${c.name}</td><td class="mono">${fmt(c.t0)}</td><td class="mono dim">${c.fired_at==null?'':fmt(c.fired_at)}</td></tr>`).join('');
  [...tb.querySelectorAll('tr[data-i]')].forEach(tr=>tr.onclick=()=>cmd('goto',{index:+tr.dataset.i}));
  const g=$('#scenes'); if(!g.childElementCount){for(let n=1;n<=62;n++){const b=document.createElement('button');b.textContent=n;b.onclick=()=>cmd('scene',{n});g.appendChild(b);}}
  [...g.children].forEach((b,k)=>b.classList.toggle('cur',S.manual_scene===k+1));
  $('#log').innerHTML=S.log.map(r=>`${r.t}  scene ${String(r.scene).padStart(2,' ')}  audio ${fmt(r.audio)}  lead ${r.lead>=0?'+':''}${r.lead} ms  ${r.name}`).join('<br>');
}
$('#bPlay').onclick=()=>cmd('toggle');$('#bNext').onclick=()=>cmd('next');$('#bPrev').onclick=()=>cmd('prev');$('#bRefire').onclick=()=>cmd('refire');$('#bBlack').onclick=()=>cmd('black');
for(const d of [-50,-10,10,50]) $('#l_'+(d>0?'p':'m')+Math.abs(d)).onclick=()=>cmd('lead',{ms:S.lead_ms+d});
$('#leadr').oninput=e=>{$('#leadv').textContent=(e.target.value>=0?'+':'')+e.target.value+' ms';};$('#leadr').onchange=e=>cmd('lead',{ms:+e.target.value});
$('#leadn').onchange=e=>cmd('lead',{ms:+e.target.value});
$('#level').oninput=e=>{$('#levelv').textContent=e.target.value;};$('#level').onchange=e=>cmd('level',{level:+e.target.value});
$('#bar').onclick=e=>{const r=e.currentTarget.getBoundingClientRect();cmd('seek',{t:(e.clientX-r.left)/r.width*S.duration});};
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;const k=e.key;
  if(k===' '){e.preventDefault();cmd('toggle');}else if(k==='n')cmd('next');else if(k==='p')cmd('prev');else if(k==='r')cmd('refire');else if(k==='b')cmd('black');
  else if(k==='[')cmd('lead',{ms:S.lead_ms-10});else if(k===']')cmd('lead',{ms:S.lead_ms+10});else if(k==='{')cmd('lead',{ms:S.lead_ms-50});else if(k==='}')cmd('lead',{ms:S.lead_ms+50});});
poll();setInterval(poll,150);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    player = None

    def log_message(self, *a):                                       # keep the terminal quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/state"):
            self._send(200, json.dumps(self.player.state()))
        else:
            self._send(200, PAGE, "text/html")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        op = body.pop("op", "")
        try:
            self._send(200, json.dumps(self.player.cmd(op, **body)))
        except Exception as e:
            self._send(400, json.dumps({"error": str(e)}))


# ----------------------------------------------------------------- main
def load_cues(path, single_scene=None, at=0.0, duration=None):
    if single_scene is not None:
        return [{"scene": single_scene, "name": f"scene {single_scene} (whole file)", "t0": at, "t1": duration or 1e9}]
    d = json.load(open(path))
    cues = [{"scene": s["scene"], "name": s.get("name", ""), "t0": float(s["t0"]), "t1": float(s["t1"])} for s in d["scenes"]]
    return sorted(cues, key=lambda c: c["t0"])


def main():
    ap = argparse.ArgumentParser(description="Play the show: audio + DMX scene cues from one clock, UI in the browser.")
    ap.add_argument("--cues", default=default_cues(), help="cues.json (default: next to this script, else repo/out/studio/cards/)")
    ap.add_argument("--audio", default=default_audio(), help="audio file (default: the first .mp3 next to this script)")
    ap.add_argument("--from", dest="start", type=int, default=1, help="start at this song number (1-based, in cue order)")
    ap.add_argument("--scene", type=int, default=None, help="ignore cues.json: one scene for the whole audio")
    ap.add_argument("--at", type=float, default=0.0, help="with --scene: audio time (s) the scene corresponds to")
    ap.add_argument("--lead-ms", type=int, default=None, help="DMX before audio, ms (default: last saved, else 0)")
    ap.add_argument("--addr", type=int, default=1)
    ap.add_argument("--hz", type=int, default=40)
    ap.add_argument("--port", default=None)
    ap.add_argument("--no-dmx", action="store_true", help="audio only (rehearsal)")
    ap.add_argument("--buffer-ms", type=int, default=100, help="audio device buffer")
    ap.add_argument("--http", type=int, default=8777, help="UI port")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    st = load_settings()
    lead = a.lead_ms if a.lead_ms is not None else int(st.get("lead_ms", 0))
    level = int(st.get("level", 255))
    if not os.path.exists(a.audio):
        sys.exit(f"audio not found: {a.audio}")
    if a.scene is None and not os.path.exists(a.cues):
        sys.exit(f"cues not found: {a.cues}\n  Render & cards -> One scene per song writes it; or run with --scene N for a single-scene show.")
    print(f"decoding {os.path.basename(a.audio)} …", flush=True)
    audio = AudioClock(a.audio, buffer_ms=a.buffer_ms)
    cues = load_cues(a.cues, single_scene=a.scene, at=a.at, duration=audio.duration)
    dmx = NullDmx() if a.no_dmx else DmxEngine(port=a.port, slots=max(MIN_SLOTS, a.addr + 6), hz=a.hz)
    player = Player(dmx, audio, cues, a.addr, lead, level=level, audio_name=os.path.basename(a.audio))
    start = max(0, min(len(cues) - 1, a.start - 1))
    player.cur = start - 1                                           # first press of Play jumps to the start cue
    Handler.player = player
    srv = ThreadingHTTPServer(("127.0.0.1", a.http), Handler)
    url = f"http://127.0.0.1:{a.http}"
    print(f"{len(cues)} cue(s) · {dmx.kind} on {dmx.port} · lead {lead:+d} ms\nUI: {url}   (Ctrl-C here to quit)", flush=True)
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    # the first Play should start at the chosen song: arm it so 'toggle' from cur=-1 jumps
    orig_cmd = player.cmd
    def cmd(op, **kw):
        if op in ("toggle", "play") and player.cur < 0 and player.manual_scene is None:
            player.jump(start); return player.state()
        return orig_cmd(op, **kw)
    player.cmd = cmd
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close(); player.shutdown()


if __name__ == "__main__":
    main()
