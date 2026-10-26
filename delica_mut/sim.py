"""Simulated F3 06 (gearbox) and 3002 (engine) computers, so everything runs without a van.

The gearbox scenario loops every 120 s: idle in P, select D, accelerate to 87 km/h, cruise in 4th
with the pedal creeping up until the lock-up releases (about 2.3 V) and re-locks once the pedal falls
back, coast down, stop. The engine scenario loops every 90 s: idle, a pull with boost, cruise, lift.
Values are synthetic demo data, not recordings.
"""

import functools
import math
import time

from . import ENGINE, GEARBOX
from .channels import SH_COEFFS, steinhart_hart
from .sessions import Session, SessionLost

LOOP = {GEARBOX: 120.0, ENGINE: 90.0}
RATIOS = {1: 0.358, 2: 0.677, 3: 1.0, 4: 1.367}   # output / input shaft speed per gear
UNLOCK_V, RELOCK_V = 2.30, 2.12                    # lock-up schedule with hysteresis (demo values)
KMH_PER_OUTPUT_RPM = 87 / 2830


class VirtualClock:
    """Deterministic clock for tests: sleep() just advances time."""

    def __init__(self, start=1_700_000_000.0):
        self.now = start

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _interp(t, points):
    if t <= points[0][0]:
        return points[0][1]
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return points[-1][1]


def _byte(x):
    return max(0, min(255, int(round(x))))


# --------------------------------------------------------------------------------- gearbox ----
SPEED = [(0, 0), (10, 0), (34, 87), (71, 87), (90, 40), (100, 0), (120, 0)]
PEDAL = [(0, .88), (10, .88), (10.5, 2.9), (20, 2.7), (34, 2.4), (36, 1.85), (50, 1.80), (57, 2.33),
         (60, 2.33), (66, 2.05), (70, 1.85), (71, .88), (120, .88)]


def _gear(v):
    return 1 if v < 18 else 2 if v < 38 else 3 if v < 60 else 4


class GearboxModel:
    STEP = 0.05

    def __init__(self):
        n = int(LOOP[GEARBOX] / self.STEP)
        locked, lf = False, 0.0
        self.lockfrac = []
        self.release_times, self.relock_times = [], []
        for i in range(n):
            t = i * self.STEP
            v, p = _interp(t, SPEED), _interp(t, PEDAL)
            if v < 45 or _gear(v) < 3:
                want = False
            elif p >= UNLOCK_V:
                want = False
            elif p <= RELOCK_V:
                want = True
            else:
                want = locked
            if want != locked:
                (self.relock_times if want else self.release_times).append(t)
            locked = want
            lf += (self.STEP / 2.0 if locked else -self.STEP / 0.6)
            lf = max(0.0, min(1.0, lf))
            self.lockfrac.append(lf)

    def state(self, t):
        loop = LOOP[GEARBOX]
        total, t = t, t % loop
        v, p = _interp(t, SPEED), _interp(t, PEDAL)
        in_park = t < 6 or t >= 112
        gear = 0 if in_park else _gear(v) if v > 0.5 else 1
        lf = self.lockfrac[min(int(t / self.STEP), len(self.lockfrac) - 1)]
        out_rpm = v / KMH_PER_OUTPUT_RPM
        if in_park:
            engine, inp, slip = 750 + 20 * math.sin(t), 750 + 20 * math.sin(t), 0
        elif v < 0.5:
            engine, inp, slip = 700, 0, 700
        else:
            inp = out_rpm / RATIOS[gear]
            unlocked_slip = 140 + 50 * max(p - .88, 0)
            slip = 5 + (1 - lf) * (unlocked_slip - 5) if gear >= 3 else min(unlocked_slip, 300)
            engine = inp + slip
        braking = 6 <= t < 10 or 90 <= t < 112
        return dict(
            engine_rpm=engine, input_rpm=inp, output_rpm=out_rpm, atf_C=38 + 28 * (1 - math.exp(-total / 900)),
            pedal_V=p, theo=100 + 300 * p, gear=gear, slip=slip, dcc=99 * lf if gear >= 3 else 0.0, v=v,
            brake=braking, idle=p < 1.0, ac=t >= 100, elc=12.1 if in_park else 13.9, d=not in_park)

    def raw(self, cmd, t):
        s = self.state(t)
        shift = {0: 25, 1: 50, 2: 101, 3: 152, 4: 203}[s["gear"]]
        sol = _byte((100 - (100.0 if s["gear"] in (1, 2) else 0.0)) * 2.55)
        table = {
            0x10: s["engine_rpm"] / 50, 0x11: s["input_rpm"] / 30, 0x12: s["output_rpm"] / 30,
            0x13: s["atf_C"] + 40, 0x14: s["pedal_V"] * 51.2, 0x15: (s["theo"] + 588) / 9.18,
            0x16: shift, 0x18: s["slip"] + 51, 0x1A: s["dcc"] * 2.55,
            0x1B: sol, 0x1D: sol, 0x1E: 255 - sol, 0x1F: 255 - sol,
            0x27: 16 if s["d"] else 1,
            0x28: 0x14 | (0x01 if s["brake"] else 0) | (0 if s["idle"] else 0x20) | (0 if s["ac"] else 0x80),
            0x2A: s["elc"] * 7.69, 0x2B: 0, 0x44: s["v"] / 2.8,
        }
        return _byte(table.get(cmd, 0))  # 96-9D fault slots and every other read-only address: 00


# ---------------------------------------------------------------------------------- engine -----
E_RPM = [(0, 850), (10, 850), (18, 3100), (22, 3200), (24, 2200), (30, 2200), (36, 850), (90, 850)]
E_PEDAL = [(0, .88), (10, .88), (11, 3.2), (22, 3.2), (24, 1.8), (30, 1.8), (31, .88), (90, .88)]
E_BOOST = [(0, 100), (10, 100), (14, 120), (20, 175), (24, 130), (30, 125), (36, 102), (90, 100)]
_COOL_TABLE = {k: [steinhart_hart(r, k) for r in range(256)] for k in SH_COEFFS}


@functools.lru_cache(maxsize=None)
def _temp_raw_cached(key, celsius):
    vals = _COOL_TABLE[key]
    return min((r for r in range(4, 252) if vals[r] is not None), key=lambda r: abs(vals[r] - celsius))


def _temp_raw(key, celsius):
    return _temp_raw_cached(key, round(celsius))


class EngineModel:
    def state(self, t):
        total, t = t, t % LOOP[ENGINE]
        rpm, ped, boost = _interp(t, E_RPM), _interp(t, E_PEDAL), _interp(t, E_BOOST)
        load = max(0.0, (ped - .88) / 2.4)
        # actual timing and sleeve position lag their targets by ~1 s
        lag = lambda f: f(max(t - 1.0, 0.0))
        tgt = lambda tt: 6 + 11 * max(0.0, (_interp(tt, E_PEDAL) - .88) / 2.4)
        sleeve = lambda tt: 18 + 50 * max(0.0, (_interp(tt, E_PEDAL) - .88) / 2.4)
        return dict(
            rpm=rpm + 8 * math.sin(total * 2.1), pedal=ped, boost=boost, baro=100.3, load=load,
            coolant=45 + 40 * (1 - math.exp(-total / 60)), air=40 + 10 * load, fuel=38 + 8 * (1 - math.exp(-total / 90)),
            batt=13.9, t_tgt=tgt(t), t_act=lag(tgt), s_tgt=sleeve(t), s_act=lag(sleeve), idle=ped < 1.0)

    def raw(self, cmd, t):
        s = self.state(t)
        idle_bits = (0x40 | 0x10) if s["idle"] else 0
        table = {
            0x00: idle_bits, 0x01: 0x40 | 0x10, 0x02: 0, 0x03: 0, 0x04: 0, 0x05: 0x10 | 0x04, 0x06: 0,
            0x10: _temp_raw("boost_air_C", s["air"]), 0x11: _temp_raw("coolant_C", s["coolant"]),
            0x12: (s["baro"] - .3) * 2.03, 0x13: s["boost"] / 1.33, 0x14: _temp_raw("fuel_C", s["fuel"]),
            0x15: 0, 0x16: s["rpm"] / 25, 0x17: s["rpm"] / 25, 0x18: s["pedal"] * 51,
            0x19: max(0.0, s["pedal"] - .9) / 2.3 * 100 * 2.56, 0x1A: s["batt"] * 13.64,
            0x1C: (30 + 40 * s["load"]) * 2.5, 0x1D: (40 - 40 * s["load"]) * 2.5, 0x1E: 2.5 * 51.2,
            0x20: s["s_tgt"] * 2.56, 0x21: s["t_act"] * 5, 0x22: s["t_tgt"] * 5, 0x24: 25 * 2.56,
            0x25: 30 * 2.56, 0x26: s["s_act"] * 2.56,
        }
        return _byte(table.get(cmd, 0))  # 50-53 fault bytes: 00 (no faults)


MODELS = {GEARBOX: GearboxModel, ENGINE: EngineModel}
IDENT = {GEARBOX: {0xFE: 0xF3, 0xFF: 0x06}, ENGINE: {0xFE: 0x30, 0xFF: 0x02}}


class SimSession(Session):
    """Same interface as a real session. `sent` records every request that reached the 'wire'."""

    def __init__(self, ecu, log=None, clock=time.time, sleep=time.sleep, latency=0.012, fail_after=None):
        super().__init__(ecu, log)
        self.model = MODELS[ecu]()
        self.clock, self.sleep, self.latency, self.fail_after = clock, sleep, latency, fail_after
        self.t0 = clock()
        self.sent = []
        self.ecu_id = "F3 06" if ecu == GEARBOX else "30 02"

    def _read(self, cmd):
        self.sleep(self.latency)
        if self.fail_after is not None and len(self.sent) >= self.fail_after:
            raise SessionLost(f"simulated dropout at request {cmd:02X}")
        self.sent.append(cmd)
        if cmd in IDENT[self.ecu]:
            return IDENT[self.ecu][cmd]
        if cmd in (0x80, 0x81, 0x82):
            return 0x00  # ROM-ID bytes are not simulated
        return self.model.raw(cmd, self.clock() - self.t0)


def sim_wake(ecu, **kw):
    return SimSession(ecu, **kw)
