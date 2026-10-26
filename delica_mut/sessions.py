"""Wake-up / ID check for the two computers, and the request path every read goes through.

Both computers share DLC pin 7 (K-line): connect to one at a time. Nothing here re-initialises a
dropped session on its own; callers decide (see recorder.Recorder(rewake=...)).
"""

from . import ECUS, ENGINE, GEARBOX
from ._vendor.kkl import proto
from .safety import Guard

BAUD = 15625
BIT_MS = 200  # 5-baud bit time

# addr: 5-baud address; idle_ms: quiet K-line before the address; sync: keyword bytes after 0x55;
# ident: reply to FE then FF.
WAKE = {
    GEARBOX: dict(addr=0x01, idle_ms=1500, sync=(0x70, 0x85), ident=(0xF3, 0x06), sync_timeout=1.5),
    ENGINE: dict(addr=0x00, idle_ms=10000, sync=(0xEF, 0x85), ident=(0x30, 0x02), sync_timeout=2.0),
}


class WakeError(RuntimeError):
    """The computer did not answer the wake-up as expected; no data requests were sent."""


class SessionLost(RuntimeError):
    """A request got no valid echo + 1-byte reply. The session is not re-opened automatically."""


class NullLog:
    def ev(self, _ev, **kw):
        pass


class Session:
    """One verified K-line session. query() is the only way a request byte can be sent."""

    def __init__(self, ecu, log=None):
        if ecu not in ECUS:
            raise ValueError(f"ecu must be one of {ECUS}")
        self.ecu = ecu
        self.log = log or NullLog()
        self.guard = Guard(ecu)
        self.ecu_id = None

    def query(self, cmd):
        self.guard.check(cmd)
        return self._read(cmd)

    def _read(self, cmd):
        raise NotImplementedError

    def read_id(self):
        ident = (self.query(0xFE), self.query(0xFF))
        self.ecu_id = f"{ident[0]:02X} {ident[1]:02X}"
        return ident

    def close(self):
        pass


class KLineSession(Session):
    """Real hardware session on top of the vendored kkl.KLine."""

    def __init__(self, kl, ecu, log=None):
        super().__init__(ecu, log)
        self.kl = kl

    def _read(self, cmd, idle_s=0.008, timeout=0.15):
        # Replies arrive ~4-5 ms after TX, so 8 ms of silence ends the read.
        echo_ok, _ = self.kl.send([cmd])
        reply = self.kl.read_until_idle(idle_s, timeout)
        if not echo_ok or len(reply) != 1:
            self.log.ev("bad_reply", cmd=f"{cmd:02X}", echo=echo_ok, reply=proto._hex(reply))
            raise SessionLost(f"no valid reply to {cmd:02X} (echo={echo_ok}, reply={proto._hex(reply)})")
        self.kl.trim()
        return reply[0][1]


def wake(kl, ecu, log=None):
    """Slow-init the computer, check the keyword bytes, then read its ID with FE/FF."""
    log = log or NullLog()
    p = WAKE[ecu]
    log.ev("wake_begin", ecu=ecu, addr=f"{p['addr']:02X}", idle_ms=p["idle_ms"], baud=BAUD)
    result, _post, sync = proto._slow_init(kl, p["addr"], BAUD, "break", None, BIT_MS,
                                           p["idle_ms"], p["sync_timeout"], False)
    got = (sync or {}).get("kb1"), (sync or {}).get("kb2")
    if got != p["sync"]:
        log.ev("wake_failed", ecu=ecu, post=result.get("post"))
        raise WakeError(f"no {ecu} handshake (expected 55 {p['sync'][0]:02X} {p['sync'][1]:02X}, "
                        f"saw '{result.get('post')}'); no requests were sent")
    kl.sleep(0.02)
    session = KLineSession(kl, ecu, log)
    ident = session.read_id()
    if ident != p["ident"]:
        raise WakeError(f"{ecu} ID was {session.ecu_id}, expected "
                        f"{p['ident'][0]:02X} {p['ident'][1]:02X}; stopping")
    log.ev("wake_ok", ecu=ecu, ecu_id=session.ecu_id, sync=f"55 {got[0]:02X} {got[1]:02X}")
    return session


class Connection:
    """Opened cable plus a wake() helper. close() always releases the break line and the port."""

    def __init__(self, dev, kl, ecu, log=None):
        self.dev, self.kl, self.ecu, self.log = dev, kl, ecu, log or NullLog()

    def wake(self):
        return wake(self.kl, self.ecu, self.log)

    def close(self):
        for cleanup in (self.dev.break_off, self.dev.close):
            try:
                cleanup()
            except Exception:
                pass
        from ._vendor.kkl.link import hires_timer
        hires_timer(False)


def connect(ecu, log=None, port=None, ftdi_serial=None, raw_bytes=False):
    """Open the cable. port: COM5 or /dev/ttyUSB0 (pyserial); ftdi_serial: D2XX serial (Windows);
    neither: first FTDI/CH340/... cable found automatically.
    raw_bytes: also log every TX/RX byte (large files)."""
    from ._vendor.kkl.interfaces import open_interface
    from ._vendor.kkl.link import KLine, hires_timer
    key = f"serial:{port}" if port else f"d2xx:{ftdi_serial}" if ftdi_serial else "auto"
    log = log or NullLog()
    hires_timer(True)
    dev = open_interface(key)
    try:
        kl = KLine(dev, log if raw_bytes else _QuietLog(log))
        kl.setup(baud=BAUD)
        kl.sleep(3)  # let the line settle after opening, as in the proven recorder
    except Exception:
        dev.close()
        hires_timer(False)
        raise
    log.ev("cable_open", backend=getattr(dev, "backend", "?"))
    return Connection(dev, kl, ecu, log)


class _QuietLog:
    """KLine logs every TX/RX byte; keep those out of the event file."""

    NOISY = {"tx", "rx", "line", "baud", "5baud_begin", "5baud_end"}

    def __init__(self, log):
        self.log = log

    def ev(self, _ev, t=None, **kw):
        if _ev not in self.NOISY:
            self.log.ev(_ev, **kw)


def open_session(ecu, log=None, sim=False, port=None, ftdi_serial=None, raw_bytes=False, sim_speed=1.0):
    """Wake the computer (or start the simulator). Returns (session, wake_fn, cleanup_fn).

    wake_fn opens a fresh session; callers only use it when re-wake was explicitly requested."""
    log = log or NullLog()
    if sim:
        import time as _time

        from .sim import SimSession
        t0 = _time.time()

        def make():
            return SimSession(ecu, log=log, clock=lambda: t0 + (_time.time() - t0) * sim_speed)
        return make(), make, (lambda: None)
    conn = connect(ecu, log=log, port=port, ftdi_serial=ftdi_serial, raw_bytes=raw_bytes)
    try:
        return conn.wake(), conn.wake, conn.close
    except Exception:
        conn.close()
        raise
