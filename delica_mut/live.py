"""delica-live: local web dashboard (stdlib http.server, no CDN) around the recorder.

    delica-live --sim            demo with the built-in simulator
    delica-live                  real cable, then pick the computer in the page
    delica-live --lan            also reachable from a phone on the same Wi-Fi (key in the URL)

Opening the page never touches the vehicle; the computer is only woken when you press Connect.
"""

import argparse
import collections
import csv
import io
import json
import secrets
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import ECUS, ENGINE, GEARBOX, __version__
from .channels import COLUMN_ADDR, TEMP_NOTE, Decoder, channel_meta, load_tables
from .decode import decoded_columns
from .events import detect_lockup_releases
from .recorder import EventLog, Recorder, default_paths, profiles_for
from .sessions import open_session

WEB = Path(__file__).parent / "web"
HISTORY_ROWS = 4000
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


class LiveHub:
    def __init__(self, outdir="logs", sim=False, sim_speed=1.0, port=None, ftdi_serial=None, tables=None,
                 rewake=0, auto_record=True):
        self.outdir, self.sim, self.sim_speed = Path(outdir), sim, sim_speed
        self.port, self.ftdi_serial, self.tables, self.rewake, self.auto_record = port, ftdi_serial, tables or {}, rewake, auto_record
        self.key = secrets.token_urlsafe(9)
        self.lock = threading.RLock()
        self.thread = None
        self.reset()

    def reset(self):
        self.status, self.detail, self.ecu, self.profile, self.ecu_id = "idle", "Not connected. Nothing has been sent to the van.", None, None, None
        self.history = collections.deque(maxlen=HISTORY_ROWS)
        self.seq, self.run_id, self.rec, self.decoder = 0, 0, None, None
        self.latest, self.last_fresh, self.markers, self.lockups = {}, {}, [], []
        self._lock_keys, self._last_detect = set(), 0.0
        self.started, self.raw_csv, self.events_path = None, None, None
        self._abort = False

    # ---- controls -----------------------------------------------------------------------------
    def connect(self, ecu, profile=None):
        if ecu not in ECUS:
            raise ValueError("ecu must be 'gearbox' or 'engine'")
        profile = profile or ("engine" if ecu == ENGINE else "gearbox-cruise")
        if profile not in profiles_for(ecu):
            raise ValueError(f"profile {profile} is not for the {ecu} computer")
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise RuntimeError("already connected; press Stop first")
            run_id = self.run_id + 1
            self.reset()
            self.run_id, self.ecu, self.profile, self.status = run_id, ecu, profile, "connecting"
            self.decoder = Decoder(ecu, tables=self.tables)
            self.detail = ("Waking the engine computer (10 s quiet line first)..." if ecu == ENGINE
                           else "Waking the gearbox computer...") if not self.sim else "Starting the simulator..."
            self.thread = threading.Thread(target=self._run, args=(ecu, profile), daemon=True)
            self.thread.start()

    def stop(self):
        with self.lock:
            if self.rec:
                self.rec.stop("stop requested")
            elif self.status == "connecting":
                self.detail = "Stop requested; finishing the wake-up, then closing."
                self._abort = True

    def set_recording(self, on):
        with self.lock:
            if not self.rec:
                raise RuntimeError("not connected")
            if on and not self.rec.recording:
                self.raw_csv, _ = default_paths(self.outdir, self.ecu, self.profile)
                self.rec.start_csv(self.raw_csv)
            elif not on:
                self.rec.stop_csv()

    def mark(self, label):
        label = (label or "").strip()[:60] or "mark"
        with self.lock:
            if not self.rec:
                raise RuntimeError("not connected")
            self.rec.mark(label)
            self.markers.append({"t": round(time.time() - self.started, 2) if self.started else 0, "label": label})

    # ---- worker -------------------------------------------------------------------------------
    def _run(self, ecu, profile):
        events = None
        cleanup = lambda: None
        try:
            csv_path, events_path = default_paths(self.outdir, ecu, profile)
            events = EventLog(events_path)
            session, wake, cleanup = open_session(ecu, events, sim=self.sim, port=self.port,
                                                  ftdi_serial=self.ftdi_serial, sim_speed=self.sim_speed)
            if self._abort:
                with self.lock:
                    self.status, self.detail = "stopped", "Stopped before the first request."
                return
            rec = Recorder(session, profile, log=events, on_row=self._on_row, wake=wake, max_rewakes=self.rewake)
            with self.lock:
                self.rec, self.ecu_id, self.started = rec, session.ecu_id, time.time()
                self.status, self.detail = "live", f"Reading the {ecu} computer. One session; it will not reconnect by itself."
                self.events_path = events_path
                if self.auto_record:
                    self.raw_csv = csv_path
                    rec.start_csv(csv_path)
            result = rec.run(None)
            with self.lock:
                lost = result["reason"].startswith(("session lost", "re-wake failed"))
                self.status = "lost" if lost else "stopped"
                self.detail = ("Reply lost, so logging stopped without reconnecting. Park, check the cable, "
                               "then press Connect again." if lost else "Stopped. The recording is saved.")
        except Exception as exc:   # WakeError, cable errors: report, never retry silently
            with self.lock:
                self.status, self.detail = "error", f"{type(exc).__name__}: {exc}"
        finally:
            cleanup()
            if events:
                events.close()
            with self.lock:
                self.rec = None

    def _on_row(self, row):
        decoded = self.decoder.decode(row.values)
        with self.lock:
            self.seq += 1
            decoded.update(seq=self.seq, t=row.elapsed_s, utc_ms=row.utc_ms, marker=row.marker)
            self.history.append(decoded)
            self.latest = {k: v for k, v in decoded.items() if v is not None}
            for addr in row.fresh:
                self.last_fresh[addr] = row.elapsed_s
            if self.ecu == GEARBOX and row.elapsed_s - self._last_detect >= 1.0:
                self._last_detect = row.elapsed_s
                self._detect_lockups()

    def _detect_lockups(self):
        rows = [r for r in self.history if r.get("dcc_slip_rpm") is not None]
        if len(rows) < 10:
            return
        ts = [r["t"] for r in rows]
        found = detect_lockup_releases(ts, [r["dcc_slip_rpm"] for r in rows],
                                       [r.get("input_rpm") for r in rows], [r.get("shift_pos") for r in rows])
        for j, i, end in found:
            key = round(ts[j], 1)
            if key in self._lock_keys:
                self._update_open_lockup(key, ts, end)
                continue
            self._lock_keys.add(key)
            r = rows[j]
            self.lockups.append({"key": key, "t": ts[j], "end": ts[end] if end is not None else None,
                                 "pedal_V": r.get("pedal_V"), "speed_kmh": r.get("speed_kmh"), "gear": r.get("shift_pos"),
                                 "engine_rpm": rows[i].get("engine_rpm"), "input_rpm": r.get("input_rpm"),
                                 "dcc_duty_pct": r.get("dcc_duty_pct")})
        self.lockups = self.lockups[-50:]

    def _update_open_lockup(self, key, ts, end):
        for ev in self.lockups:
            if ev["key"] == key and ev["end"] is None and end is not None:
                ev["end"] = ts[end]

    # ---- data for the HTTP layer --------------------------------------------------------------
    def state(self):
        with self.lock:
            ecu = self.ecu
            elapsed = round(self.history[-1]["t"], 1) if self.history else 0
            rate = None
            if len(self.history) > 5:
                h = list(self.history)[-25:]
                rate = round((len(h) - 1) / (h[-1]["t"] - h[0]["t"]), 1) if h[-1]["t"] > h[0]["t"] else None
            ages = {}
            if ecu:
                ages = {col: round(elapsed - self.last_fresh[addr], 1) for col, addr in COLUMN_ADDR[ecu].items()
                        if addr in self.last_fresh}
            return {
                "version": __version__, "status": self.status, "detail": self.detail, "ecu": ecu, "profile": self.profile,
                "ecu_id": self.ecu_id, "sim": self.sim, "run_id": self.run_id, "seq": self.seq, "elapsed_s": elapsed,
                "rows_per_s": rate, "recording": bool(self.rec and self.rec.recording),
                "csv_name": self.raw_csv.name if self.raw_csv else None, "rows_written": self.rec.rows_written if self.rec else 0,
                "latest": self.latest, "ages": ages, "lockups": list(self.lockups), "markers": list(self.markers),
                "profiles": {e: profiles_for(e) for e in ECUS},
                "temperature_source": ("user table" if self.tables else "provisional curve"),
                "temperature_note": TEMP_NOTE,
            }

    def history_since(self, since=0, limit=1500):
        with self.lock:
            rows = [r for r in self.history if r["seq"] > since][-limit:]
            return {"run_id": self.run_id, "seq": self.seq, "rows": rows}

    def raw_csv_bytes(self):
        with self.lock:
            path = self.raw_csv
        if not path or not Path(path).is_file():
            return None
        return Path(path).read_bytes()

    def decoded_csv_bytes(self):
        raw = self.raw_csv_bytes()
        if raw is None:
            return None
        from .decode import decode_raw_rows
        with self.lock:
            ecu, decoder = self.ecu, self.decoder
        rows = decode_raw_rows(list(csv.DictReader(io.StringIO(raw.decode("utf-8")))), ecu, decoder)
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=decoded_columns(ecu))
        w.writeheader()
        w.writerows(rows)
        return out.getvalue().encode("utf-8")

    def summary_markdown(self):
        with self.lock:
            path, ecu = self.raw_csv, self.ecu
        if not path or not Path(path).is_file():
            return None
        from .ai import summarize, to_markdown
        return to_markdown(summarize(path, ecu, tables=self.tables)).encode("utf-8")


# --------------------------------------------------------------------------------------- HTTP ---
def make_handler(hub, lan):
    class Handler(BaseHTTPRequestHandler):
        server_version = "delica-live"

        def log_message(self, *args):
            pass

        def _send(self, code, body, mime="application/json", extra=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self):
            host = self.headers.get("Host") or ""
            host = host.split("]")[0] + "]" if host.startswith("[") else host.rsplit(":", 1)[0]
            return lan or host in LOCAL_HOSTS   # blocks DNS-rebinding when only local

        def _token_ok(self, qs):
            given = self.headers.get("X-Token") or (qs.get("key") or [""])[0]
            return secrets.compare_digest(given, hub.key)

        def do_GET(self):
            url = urlsplit(self.path)
            qs = parse_qs(url.query)
            if not self._host_ok():
                return self._send(403, {"error": "bad Host header"})
            if url.path in ("/", "/index.html"):
                if lan and not self._token_ok(qs):
                    return self._send(403, "Open the URL printed by delica-live (it contains ?key=...).", "text/plain")
                html = (WEB / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", hub.key)
                return self._send(200, html, "text/html; charset=utf-8")
            if url.path.startswith("/api/") and lan and not self._token_ok(qs):
                return self._send(403, {"error": "missing key"})
            if url.path == "/api/state":
                return self._send(200, hub.state())
            if url.path == "/api/history":
                return self._send(200, hub.history_since(int((qs.get("since") or ["0"])[0] or 0)))
            if url.path == "/api/channels":
                ecu = (qs.get("ecu") or [GEARBOX])[0]
                if ecu not in ECUS:
                    return self._send(400, {"error": "unknown ecu"})
                return self._send(200, {"ecu": ecu, "channels": channel_meta(ecu), "temperature_note": TEMP_NOTE})
            if url.path in ("/api/download.csv", "/api/summary.md"):
                if url.path == "/api/summary.md":
                    body, mime, name = hub.summary_markdown(), "text/markdown", "delica-summary.md"
                elif (qs.get("decoded") or ["0"])[0] == "1":
                    body, mime, name = hub.decoded_csv_bytes(), "text/csv", "delica-decoded.csv"
                else:
                    body, mime, name = hub.raw_csv_bytes(), "text/csv", (hub.raw_csv.name if hub.raw_csv else "delica.csv")
                if body is None:
                    return self._send(404, {"error": "no recording yet"})
                return self._send(200, body, mime, {"Content-Disposition": f'attachment; filename="{name}"'})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            url = urlsplit(self.path)
            qs = parse_qs(url.query)
            if not self._host_ok() or not self._token_ok(qs):
                return self._send(403, {"error": "bad token or host"})
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                return self._send(415, {"error": "send application/json"})
            try:
                size = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(min(size, 4096)) or b"{}")
                if url.path == "/api/connect":
                    hub.connect(body.get("ecu"), body.get("profile"))
                elif url.path == "/api/stop":
                    hub.stop()
                elif url.path == "/api/record":
                    hub.set_recording(bool(body.get("on")))
                elif url.path == "/api/mark":
                    hub.mark(str(body.get("label", "")))
                else:
                    return self._send(404, {"error": "not found"})
            except (ValueError, RuntimeError) as exc:
                return self._send(400, {"error": str(exc)})
            self._send(200, {"ok": True})

    return Handler


def lan_address():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))   # no packet is sent; just picks the outgoing interface
            return s.getsockname()[0]
    except OSError:
        return "your-computer-ip"


def serve(hub, host="127.0.0.1", port=8765, lan=False):
    server = ThreadingHTTPServer((host, port), make_handler(hub, lan))
    server.daemon_threads = True
    return server


def main(argv=None):
    ap = argparse.ArgumentParser(prog="delica-live", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim", action="store_true", help="demo with the built-in simulator, no hardware")
    ap.add_argument("--sim-speed", type=float, default=1.0, help="run the simulated drive faster (e.g. 3)")
    ap.add_argument("--lan", action="store_true", help="listen on the local network for a phone (key required)")
    ap.add_argument("--http-port", type=int, default=8765)
    ap.add_argument("--port", help="cable serial port, e.g. COM5 or /dev/ttyUSB0 (default: first cable found)")
    ap.add_argument("--ftdi-serial", help="FTDI serial number for the Windows D2XX driver")
    ap.add_argument("--out", default="logs", help="recordings folder (default ./logs)")
    ap.add_argument("--rewake", type=int, default=0, metavar="N", help="explicitly allow N automatic re-wakes (default 0)")
    ap.add_argument("--temp-tables", help="JSON with your own 256-entry temperature tables")
    ap.add_argument("--no-record", action="store_true", help="do not start recording automatically on connect")
    ap.add_argument("--open", action="store_true", help="open the page in your browser")
    a = ap.parse_args(argv)
    hub = LiveHub(a.out, a.sim, a.sim_speed, a.port, a.ftdi_serial, load_tables(a.temp_tables), a.rewake, not a.no_record)
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    server = serve(hub, host, a.http_port, a.lan)
    port = server.server_address[1]
    local = f"http://127.0.0.1:{port}/" + (f"?key={hub.key}" if a.lan else "")
    print(f"delica-live {__version__}" + (" (SIMULATOR)" if a.sim else ""))
    print(f"  This computer:  {local}")
    if a.lan:
        print(f"  Phone (same Wi-Fi): http://{lan_address()}:{port}/?key={hub.key}")
        print("  Anyone with that key can see the data and start/stop logging. Stop the program when done.")
    print("  Nothing is sent to the van until you press Connect in the page. Ctrl+C to quit.")
    if a.open:
        webbrowser.open(local)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        hub.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
