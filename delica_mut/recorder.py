"""Profile-driven recorder: wide CSV (latest value of every polled request + a `fresh` column) and a
JSONL event log. Read-only; a dropped session stops the run unless re-wake was explicitly requested.
"""

import csv
import datetime
import json
import platform
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import ENGINE, GEARBOX, __version__
from .safety import ENGINE_READS, ENGINE_ROM_ID_READS, GEARBOX_READS, check_profile_ids
from .sessions import NullLog, SessionLost


@dataclass(frozen=True)
class Profile:
    name: str
    ecu: str
    fast: tuple      # read every cycle
    slow: tuple      # read round-robin, `slice` per cycle
    slice: int

    @property
    def ids(self):
        return sorted(set(self.fast) | set(self.slow))


_ALL_GEARBOX = tuple(sorted(GEARBOX_READS))
_CRUISE_FAST = (0x10, 0x11, 0x18, 0x1A, 0x14, 0x28, 0x44, 0x12, 0x16)   # rpm, input, slip, DCC duty, pedal, flags, speed
_CRUISE_SLOW = (0x13, 0x15, 0x1B, 0x1D, 0x1E, 0x1F, 0x27, 0x2A, 0x2B) + tuple(range(0x96, 0x9E))
_FLAG_FAST = (0x14, 0x20, 0x17, 0x27, 0x28, 0x2B, 0x31, 0x3B, 0x4B, 0x84, 0xA2, 0xA5, 0xA6, 0xA8, 0xA9, 0xAA, 0xAC, 0xA1)
_ENGINE_FAST = (0x17, 0x16, 0x18, 0x13, 0x21, 0x22, 0x1C, 0x20, 0x26, 0x24, 0x1A, 0x15)
_FULL_FAST = (0x10, 0x11, 0x12, 0x14, 0x18, 0x1A, 0x28, 0x44, 0x16, 0x13)

PROFILES = {p.name: p for p in (
    Profile("gearbox-cruise", GEARBOX, _CRUISE_FAST, _CRUISE_SLOW, 2),
    Profile("gearbox-full", GEARBOX, _FULL_FAST, tuple(i for i in _ALL_GEARBOX if i not in _FULL_FAST), 16),
    # switch hunt: every byte that toggled in the parked brake / pedal test, then everything else slowly
    Profile("gearbox-flags", GEARBOX, _FLAG_FAST, tuple(i for i in _ALL_GEARBOX if i not in _FLAG_FAST), 8),
    Profile("engine", ENGINE, _ENGINE_FAST, tuple(sorted(ENGINE_READS - set(_ENGINE_FAST))), 4),
)}
for _p in PROFILES.values():
    check_profile_ids(_p.ecu, _p.ids)  # import-time proof that no profile can request a blocked byte


def profiles_for(ecu):
    return [n for n, p in PROFILES.items() if p.ecu == ecu]


class EventLog:
    """JSONL events with wall-clock seconds. Also usable as the log object of the vendored KLine."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "w", encoding="utf-8")
        self._lock = threading.Lock()

    def ev(self, _ev, t=None, **kw):
        rec = {"t": round(time.time(), 3), "ev": _ev, **kw}
        with self._lock:
            self._f.write(json.dumps(rec, default=str) + "\n")
            self._f.flush()

    def close(self):
        with self._lock:
            self._f.close()


def csv_header(profile):
    return ["utc_ms", "elapsed_s", "cycle", "marker", "fresh"] + [f"r{i:02X}" for i in profile.ids]


def _safe_label(text):
    text = text.strip()[:60].replace("\n", " ")
    return "'" + text if text[:1] in "=+-@" else text


@dataclass
class Row:
    utc_ms: int
    elapsed_s: float
    cycle: int
    marker: str
    fresh: list
    values: dict   # {request: raw byte}, latest value of every request seen so far


class Recorder:
    def __init__(self, session, profile, *, clock=time.time, log=None, on_row=None,
                 wake=None, max_rewakes=0, rom_id=True):
        if isinstance(profile, str):
            profile = PROFILES[profile]
        if session.ecu != profile.ecu:
            raise ValueError(f"profile {profile.name} is for the {profile.ecu}, session is {session.ecu}")
        self.session, self.profile, self.clock = session, profile, clock
        self.log = log or NullLog()
        self.on_row, self.wake, self.rewakes_left, self.rom_id = on_row, wake, max_rewakes, rom_id
        self.latest, self.cycle, self.marker, self.reason = {}, 0, "start", None
        self.start = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._pending_marks = []
        self._csv = self._csv_file = None
        self.csv_path = None
        self.rows_written = 0

    @property
    def recording(self):
        return self._csv is not None

    # -- controls (thread-safe) ----------------------------------------------------------------
    def mark(self, label):
        with self._lock:
            self._pending_marks.append(label)

    def stop(self, reason="stop requested"):
        self.reason = self.reason or reason
        self._stop.set()

    def start_csv(self, path):
        self.stop_csv()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._csv_file = open(path, "w", newline="", encoding="utf-8")
            self._csv = csv.writer(self._csv_file)
            self._csv.writerow(csv_header(self.profile))
            self.csv_path = path
        self.log.ev("csv_start", file=path.name)
        return path

    def stop_csv(self):
        with self._lock:
            if self._csv_file:
                self._csv_file.close()
                self._csv = self._csv_file = None
                self.log.ev("csv_stop", file=self.csv_path.name, rows=self.rows_written)

    # -- main loop -----------------------------------------------------------------------------
    def run(self, seconds=None):
        self.start = self.clock()
        self.log.ev("run_start", version=__version__, ecu=self.profile.ecu, profile=self.profile.name,
                    ecu_id=self.session.ecu_id, ids=[f"{i:02X}" for i in self.profile.ids],
                    rewake_allowed=self.rewakes_left, python=platform.python_version())
        if self.rom_id and self.profile.ecu == ENGINE:
            self._read_rom_ids()
        slow, pos = list(self.profile.slow), 0
        try:
            while not self._stop.is_set() and (seconds is None or self.clock() - self.start < seconds):
                self._apply_marks()
                self.cycle += 1
                stamp = self.clock()
                batch = list(self.profile.fast) + [slow[(pos + k) % len(slow)] for k in range(self.profile.slice)] \
                    if slow else list(self.profile.fast)
                pos = (pos + self.profile.slice) % len(slow) if slow else 0
                fresh = []
                try:
                    for cmd in batch:
                        self.latest[cmd] = self.session.query(cmd)
                        fresh.append(cmd)
                except SessionLost as exc:
                    self._emit(stamp, fresh)  # keep what this cycle did read
                    if not self._try_rewake(exc):
                        break
                    continue
                self._emit(stamp, fresh)
            else:
                self.reason = self.reason or "duration reached"
        finally:
            self.stop_csv()
            self.log.ev("run_end", cycles=self.cycle, reason=self.reason)
        return {"cycles": self.cycle, "reason": self.reason, "csv": str(self.csv_path) if self.csv_path else None}

    def _read_rom_ids(self):
        rom = []
        try:
            for cmd in ENGINE_ROM_ID_READS:   # one-shot per session, guarded in safety.Guard
                rom.append(f"{self.session.query(cmd):02X}")
        except SessionLost as exc:
            self.log.ev("rom_id_failed", error=str(exc))
            return
        self.log.ev("rom_id_read", requests="80 81 82", bytes=" ".join(rom))

    def _apply_marks(self):
        with self._lock:
            marks, self._pending_marks = self._pending_marks, []
        for label in marks:
            self.marker = _safe_label(label)
            self.log.ev("marker", label=self.marker, elapsed_s=round(self.clock() - self.start, 2))

    def _emit(self, stamp, fresh):
        if not fresh:
            return
        row = Row(int(stamp * 1000), round(stamp - self.start, 2), self.cycle, self.marker, fresh, dict(self.latest))
        with self._lock:
            if self._csv:
                self._csv.writerow([row.utc_ms, row.elapsed_s, row.cycle, row.marker,
                                    " ".join(f"{c:02X}" for c in fresh)]
                                   + [self.latest.get(i, "") for i in self.profile.ids])
                self._csv_file.flush()
                self.rows_written += 1
        if self.on_row:
            self.on_row(row)

    def _try_rewake(self, exc):
        self.log.ev("session_lost", error=str(exc), rewakes_left=self.rewakes_left)
        if self.wake is None or self.rewakes_left <= 0:
            self.reason = f"session lost: {exc} (no automatic re-wake; start a new run while parked)"
            return False
        self.rewakes_left -= 1
        self.log.ev("rewake_attempt", explicit_flag=True)
        try:
            self.session = self.wake()
        except Exception as err:   # WakeError or cable error: stop, never loop
            self.reason = f"re-wake failed: {err}"
            self.log.ev("rewake_failed", error=str(err))
            return False
        self.log.ev("rewake_ok", ecu_id=self.session.ecu_id)
        return True


def default_paths(outdir, ecu, profile):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = Path(outdir) / f"{stamp}_{ecu}_{profile}"
    return base.with_suffix(".csv"), base.with_suffix(".events.jsonl")
