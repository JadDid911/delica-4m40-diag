"""Channel definitions (data) and decoders for the gearbox (F3 06) and engine (3002) computers.

Names and scales were cross-checked against the MMC-Reader diagnostic database and then compared
with recordings from a real van; this project is not affiliated with MMC-Reader. Only the resulting
facts are published here (address, name, unit, scale, confidence, evidence). No third-party lookup
tables are shipped: the three engine temperature channels use a three-coefficient curve (provisional)
or a table the user supplies locally, see load_tables().

Confidence:
  high        formula agrees with controlled on-vehicle behaviour
  medium      consistent with the vehicle, but no independent reference (meter, GPS, probe)
  low         formula comes from the profile only; the quantity was not verified
  unverified  documented but never exercised on a van
  provisional fitted curve, about +/-3 C, independent calibration pending
"""

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import ENGINE, GEARBOX

SHIFT_POSITION = {0: "R", 25: "N/P", 50: "1st", 101: "2nd", 152: "3rd", 203: "4th"}
INHIBITOR = {1: "P", 2: "R", 16: "D"}

TEMP_NOTE = ("provisional: Steinhart-Hart curve (about +/-3 C) fitted to the MMC-Reader diagnostic database "
             "conversion; matched this project's van at engine-off (coolant 43 C, boost-air 43 C, fuel 38 C); "
             "independent on-vehicle calibration pending")
# x = raw (valid 4..251); r = x/(255-x); T = 1/(a + b*ln r + c*ln(r)^3) - 273.15 C
SH_COEFFS = {
    "coolant_C": (0.003283411914678006, 0.0002955901114276845, -1.410236045157784e-06, 2.5),
    "boost_air_C": (0.003386537359081624, 0.00031393935933488813, -5.468043254925917e-06, 3.0),
    "fuel_C": (0.0034228831925160533, 0.00032578172126727185, -5.123702653933929e-06, 3.4),
}
SH_RAW_RANGE = (4, 251)
SH_VALID_C = (-20.0, 110.0)


@dataclass(frozen=True)
class Bit:
    key: str
    name: str
    mask: int
    confidence: str
    evidence: str = ""
    active_low: bool = False


@dataclass(frozen=True)
class Channel:
    ecu: str
    addr: int
    key: str
    name: str
    unit: str
    kind: str = "linear"          # linear | lookup | curve | bits | hex | slip
    mul: float = 1.0
    div: float = 1.0
    offset: float = 0.0
    digits: int = 1
    formula: str = ""
    confidence: str = "low"
    evidence: str = ""
    lookup: dict = field(default_factory=dict, hash=False, compare=False)
    bits: tuple = ()

    @property
    def raw_key(self):
        return self.key.replace("_C", "_raw")

    @property
    def columns(self):
        if self.kind == "bits":
            return [b.key for b in self.bits]
        if self.kind == "curve":
            return [self.key, self.raw_key]
        if self.kind == "slip":
            return [self.key, self.key.replace("_rpm", "_sat")]
        return [self.key]


def _lin(ecu, addr, key, name, unit, formula, conf, evidence, mul=1.0, div=1.0, offset=0.0, digits=1):
    return Channel(ecu, addr, key, name, unit, "linear", mul, div, offset, digits, formula, conf, evidence)


G = GEARBOX
E = ENGINE

CHANNELS = (
    # ---- gearbox F3 06 ---------------------------------------------------------------------------
    _lin(G, 0x10, "engine_rpm", "Engine speed (crank angle sensor)", "rpm", "raw x 50", "high",
         "0 engine-off; tracks revs; within ~11 rpm of 30 x raw 20 over 4378 drive samples", mul=50, digits=0),
    _lin(G, 0x11, "input_rpm", "Input shaft (turbine) speed", "rpm", "raw x 30", "high",
         "0 when stopped in D, follows engine in N/P, follows output speed by gear ratio", mul=30, digits=0),
    _lin(G, 0x12, "output_rpm", "Output shaft speed", "rpm", "raw x 30", "high",
         "0 in every parked capture; gear-dependent ratio to input speed", mul=30, digits=0),
    _lin(G, 0x13, "atf_C", "ATF temperature", "C", "raw - 40", "medium",
         "27 C engine-off, 31-33 C warm-up, 62-68 C on the drive; no probe reference", offset=-40, digits=0),
    _lin(G, 0x14, "pedal_V", "Accelerator pedal sensor", "V", "raw / 51.2", "high",
         "0.88 V released, 2.93 V held in parked tests; voltage not meter-checked", div=51.2, digits=3),
    _lin(G, 0x15, "theo_pressure", "Theoretical pressure (not a measured pressure)", "kPa",
         "raw x 9.18 - 588", "low", "profile quantity only; can be negative; do not clamp",
         mul=9.18, offset=-588, digits=1),
    Channel(G, 0x16, "shift_pos", "Shift position", "", "lookup", formula="lookup", confidence="high",
            evidence="73/73 fresh drive samples agree with gear from shaft ratios", lookup=SHIFT_POSITION),
    Channel(G, 0x18, "dcc_slip_rpm", "Damper clutch (lock-up) slip", "rpm", "slip", mul=1, offset=-51,
            digits=0, formula="raw - 51 (raw 0 / 255 saturate)", confidence="high",
            evidence="matches 50 x raw10 - 30 x raw11 within 50 rpm in 2129/2149 unsaturated samples"),
    _lin(G, 0x1A, "dcc_duty_pct", "Damper clutch (lock-up) solenoid duty", "%", "raw / 2.55", "medium",
         "99 % locked and 0 % released in drive 1; no electrical measurement", div=2.55),
    _lin(G, 0x1B, "sol_2nd_pct", "Secondary (2nd) solenoid duty", "%", "100 - raw / 2.55", "low",
         "profile only; varies with operating state", mul=-1, div=2.55, offset=100),
    _lin(G, 0x1D, "sol_LR_pct", "Low and reverse solenoid duty", "%", "100 - raw / 2.55", "low",
         "profile only; varies with operating state", mul=-1, div=2.55, offset=100),
    _lin(G, 0x1E, "sol_OD_pct", "Overdrive solenoid duty", "%", "100 - raw / 2.55", "low",
         "profile only; varies with operating state", mul=-1, div=2.55, offset=100),
    _lin(G, 0x1F, "sol_UD_pct", "Underdrive solenoid duty", "%", "100 - raw / 2.55", "low",
         "profile only; varies with operating state", mul=-1, div=2.55, offset=100),
    Channel(G, 0x27, "inhibitor", "Inhibitor (selector) switch", "", "lookup", formula="lookup",
            confidence="medium", evidence="1 in every parked capture, 1/2/16 on the drive; no labelled selector test",
            lookup=INHIBITOR),
    Channel(G, 0x28, "flags_28", "Switch flags", "", "bits", formula="bit masks", confidence="mixed", bits=(
        Bit("brake", "Brake (stop lamp) switch", 0x01, "high", "matches an independent brake bit in 512/515 parked cycles"),
        Bit("hold_sw", "STD/HOLD switch", 0x02, "unverified", "never exercised"),
        Bit("tf_low", "Transfer low (T/F) switch", 0x08, "unverified", "never exercised"),
        Bit("idle_pos", "Idle position (pedal released)", 0x20, "high",
            "clears with pedal released, sets on pedal, 24/24 and 40/40 fresh samples", active_low=True),
        Bit("od_off_sig", "O/D OFF signal", 0x40, "unverified", "never exercised"),
        Bit("ac_relay", "A/C relay", 0x80, "high", "follows A/C compressor cycling in the parked test", active_low=True),
    )),
    _lin(G, 0x2A, "elc_relay_V", "ELC relay voltage", "V", "raw / 7.69", "medium",
         "12.1 V engine-off, higher running; relay-circuit voltage, not a battery-terminal reading",
         div=7.69, digits=2),
    Channel(G, 0x2B, "flags_2B", "Switch flags 2", "", "bits", formula="bit masks", confidence="unverified", bits=(
        Bit("od_off_sw", "O/D OFF switch", 0x04, "unverified", "never exercised"),)),
    _lin(G, 0x44, "speed_kmh", "Vehicle speed", "km/h", "raw x 2.8", "medium",
         "0 parked; follows output shaft; 0-89.6 km/h on the drive; no GPS reference", mul=2.8),
) + tuple(
    Channel(G, a, f"fault_{a:02X}", f"A/T fault slot {a - 0x95}", "hex", "hex", formula="hex byte (00/FF = none)",
            confidence="low", evidence="all slots empty in every recording; raw byte only, no descriptions")
    for a in range(0x96, 0x9E)
) + (
    # ---- engine 3002 -----------------------------------------------------------------------------
    Channel(E, 0x10, "boost_air_C", "Boost air temperature", "C", "curve", digits=1,
            formula="Steinhart-Hart curve or user table", confidence="provisional", evidence=TEMP_NOTE),
    Channel(E, 0x11, "coolant_C", "Coolant temperature", "C", "curve", digits=1,
            formula="Steinhart-Hart curve or user table", confidence="provisional", evidence=TEMP_NOTE),
    _lin(E, 0x12, "baro_kPa", "Barometric pressure", "kPa", "raw / 2.03 + 0.3", "medium",
         "100.3 kPa engine-off; plausible; no reference", div=2.03, offset=0.3),
    _lin(E, 0x13, "boost_kPa", "Boost pressure sensor (absolute)", "kPa", "raw x 1.33", "medium",
         "99.75 kPa engine-off and near ambient at idle; under-load boost not yet recorded", mul=1.33),
    Channel(E, 0x14, "fuel_C", "Fuel temperature", "C", "curve", digits=1,
            formula="Steinhart-Hart curve or user table", confidence="provisional", evidence=TEMP_NOTE),
    _lin(E, 0x15, "speed_kmh", "Vehicle speed", "km/h", "raw", "unverified",
         "0 in every (parked) engine recording; not yet driven", digits=0),
    _lin(E, 0x16, "rpm_backup", "Engine speed (backup)", "rpm", "raw x 25", "medium",
         "tracks the primary speed signal", mul=25, digits=0),
    _lin(E, 0x17, "rpm", "Engine speed", "rpm", "raw x 25", "high",
         "750-900 rpm at idle, matching the observed idle", mul=25, digits=0),
    _lin(E, 0x18, "pedal_V", "Accelerator pedal sensor", "V", "raw / 51", "high",
         "0.88 V released, 3.47-3.51 V held", div=51, digits=2),
    _lin(E, 0x19, "pedal_pct", "Accelerator pedal position", "%", "raw / 2.56", "medium",
         "0 % released at idle", div=2.56, digits=1),
    _lin(E, 0x1A, "battery_V", "Battery voltage", "V", "raw / 13.64", "medium",
         "12.8 V key-on, 13.6-14.2 V running", div=13.64, digits=2),
    _lin(E, 0x1C, "tcv_duty_pct", "Timing control valve duty", "%", "raw / 2.5", "low",
         "profile only", div=2.5),
    _lin(E, 0x1D, "egr_target_pct", "Target EGR", "%", "raw / 2.5", "low", "profile only", div=2.5),
    _lin(E, 0x1E, "inj_adjust_V", "Injection adjust value", "V", "raw / 51.2", "low",
         "profile only; 2.5 V at mid-scale raw 128", div=51.2, digits=2),
    _lin(E, 0x20, "sleeve_target_pct", "Control sleeve position target", "%", "raw / 2.56", "medium",
         "moves with load; sequential reads cannot resolve fast tracking", div=2.56),
    _lin(E, 0x21, "timing_actual_CA", "Injection timing actual", "deg CA", "raw / 5", "medium",
         "actual generally followed target at idle (profile also offers % and V views of the same byte)", div=5),
    _lin(E, 0x22, "timing_target_CA", "Injection timing target", "deg CA", "raw / 5", "medium",
         "see actual timing", div=5),
    _lin(E, 0x24, "ge_duty_pct", "GE actuator duty", "%", "raw / 2.56", "low", "profile only", div=2.56),
    _lin(E, 0x25, "egr_duty_pct", "EGR duty", "%", "raw / 2.56", "low", "profile only", div=2.56),
    _lin(E, 0x26, "sleeve_actual_pct", "Control sleeve position actual", "%", "raw / 2.56", "medium",
         "varies more during rough running; sequential reads", div=2.56),
    Channel(E, 0x00, "switches_00", "Switch byte 00", "", "bits", formula="bit masks", confidence="mixed", bits=(
        Bit("idle_sw1", "Idle switch 1", 0x40, "low",
            "read Off with the pedal released on the test van while fault 23 (idle switch 1) was set; treat as suspect"),
        Bit("idle_sw2", "Idle switch 2", 0x10, "medium", "Off with pedal held, On when released"),
        Bit("ac_sw", "A/C switch", 0x04, "unverified"),
        Bit("st_sw", "Starter (ST) switch", 0x01, "unverified"))),
    Channel(E, 0x01, "switches_01", "Switch byte 01", "", "bits", formula="bit masks", confidence="low", bits=(
        Bit("ig_sw", "Ignition switch", 0x40, "low"),
        Bit("control_relay", "Control relay", 0x10, "low"),
        Bit("ac_relay", "A/C relay", 0x04, "unverified"))),
    Channel(E, 0x02, "switches_02", "Switch byte 02", "", "bits", formula="bit masks", confidence="low", bits=(
        Bit("fan_relay_lo", "Fan relay LO", 0x10, "unverified"),
        Bit("glow_relay", "Glow plug relay", 0x01, "low"))),
    Channel(E, 0x03, "switches_03", "Switch byte 03", "", "bits", formula="bit masks", confidence="low", bits=(
        Bit("throttle_sol", "Throttle valve solenoid", 0x40, "low"),
        Bit("throttle_sol2", "Throttle valve solenoid 2", 0x10, "low"),
        Bit("check_lamp", "Engine check lamp", 0x04, "low"),
        Bit("glow_lamp", "Glow lamp", 0x01, "low"))),
    Channel(E, 0x04, "switches_04", "Switch byte 04", "", "bits", formula="bit masks", confidence="low", bits=(
        Bit("neutral_sw", "Neutral switch", 0x10, "unverified"),
        Bit("abs_sw", "ABS switch", 0x04, "unverified"),
        Bit("fuel_cut_valve", "Fuel cut valve", 0x01, "low"))),
    Channel(E, 0x05, "switches_05", "Switch byte 05", "", "bits", formula="bit masks", confidence="low", bits=(
        Bit("egr_sol2", "EGR solenoid 2", 0x40, "low"),
        Bit("is_at", "Automatic transmission (set = A/T)", 0x10, "low"),
        Bit("is_van", "Vehicle type (set = van)", 0x04, "low"))),
    Channel(E, 0x06, "switches_06", "Switch byte 06", "", "bits", formula="bit masks", confidence="low", bits=(
        Bit("coolant_temp_sw", "Coolant temperature switch", 0x40, "unverified"),
        Bit("ac_temp_signal", "A/C temperature signal", 0x10, "unverified"),
        Bit("intercooler_fan", "Intercooler fan", 0x04, "unverified"))),
) + tuple(
    Channel(E, a, f"fault_{a:02X}", f"Fault bit byte {a:02X}", "hex", "hex", formula="hex byte, bit = one fault",
            confidence="high" if a == 0x51 else "low",
            evidence=("bit 04 = blink code 23 (idle switch 1) on the test van" if a == 0x51
                      else "no bits set in recordings; look the bits up in your service manual"))
    for a in range(0x50, 0x54)
)

BY_ECU = {ecu: tuple(c for c in CHANNELS if c.ecu == ecu) for ecu in (GEARBOX, ENGINE)}
BY_ADDR = {ecu: {c.addr: c for c in chans} for ecu, chans in BY_ECU.items()}
# decoded column -> the request address(es) that refresh it
COLUMN_ADDR = {ecu: {col: c.addr for c in chans for col in c.columns} for ecu, chans in BY_ECU.items()}
DERIVED_COLUMNS = {GEARBOX: [], ENGINE: ["boost_gauge_kPa"]}


def columns(ecu):
    return [col for c in BY_ECU[ecu] for col in c.columns] + DERIVED_COLUMNS[ecu]


# ---------------------------------------------------------------------------------------------
# temperature conversion
# ---------------------------------------------------------------------------------------------
def steinhart_hart(raw, key):
    """Provisional curve. None for raw outside 4..251 or a result outside -20..110 C."""
    a, b, c, _ = SH_COEFFS[key]
    if not SH_RAW_RANGE[0] <= raw <= SH_RAW_RANGE[1]:
        return None
    lg = math.log(raw / (255 - raw))
    denom = a + b * lg + c * lg ** 3
    if denom <= 0:
        return None
    t = 1 / denom - 273.15
    return t if SH_VALID_C[0] <= t <= SH_VALID_C[1] else None


TABLE_KEYS = tuple(SH_COEFFS)


def load_tables(path=None):
    """Optional user-supplied 256-entry tables: {"coolant_C": [...], "boost_air_C": [...], "fuel_C": [...]}.

    Search order: explicit path, $DELICA_TEMP_TABLES, ./temperature_tables.json,
    ~/.delica-4m40-diag/temperature_tables.json. Index = raw byte; null = no reading. Returns {} if none.
    """
    candidates = [path, os.environ.get("DELICA_TEMP_TABLES"), "temperature_tables.json",
                  Path.home() / ".delica-4m40-diag" / "temperature_tables.json"]
    for cand in candidates:
        if cand and Path(cand).is_file():
            data = json.loads(Path(cand).read_text(encoding="utf-8"))
            out = {}
            for key in TABLE_KEYS:
                table = data.get(key)
                if table is None:
                    continue
                if not isinstance(table, list) or len(table) != 256:
                    raise ValueError(f"{cand}: {key} must be a list of 256 numbers (index = raw byte)")
                out[key] = [None if v is None else float(v) for v in table]
            return out
        if cand is path and path:
            raise FileNotFoundError(path)
    return {}


# ---------------------------------------------------------------------------------------------
# decoder
# ---------------------------------------------------------------------------------------------
class Decoder:
    """raw {addr: byte} -> ordered {column: value}. Missing inputs give None."""

    def __init__(self, ecu, tables=None, raw_temps=False):
        self.ecu = ecu
        self.tables = tables or {}
        self.raw_temps = raw_temps
        self.channels = BY_ECU[ecu]
        self.columns = columns(ecu)

    def temperature_source(self, key):
        if self.raw_temps:
            return "raw"
        return "user table" if key in self.tables else "provisional curve"

    def temperature(self, raw, key):
        if self.raw_temps or raw is None:
            return None
        if key in self.tables:
            return self.tables[key][raw]
        return steinhart_hart(raw, key)

    def decode(self, raw):
        out = dict.fromkeys(self.columns)
        for ch in self.channels:
            v = raw.get(ch.addr)
            if v is None:
                continue
            if ch.kind == "linear":
                out[ch.key] = round(v * ch.mul / ch.div + ch.offset, ch.digits) if ch.digits else int(round(v * ch.mul / ch.div + ch.offset))
            elif ch.kind == "lookup":
                out[ch.key] = ch.lookup.get(v, v)
            elif ch.kind == "slip":
                out[ch.key] = max(-51, min(204, v - 51))
                out[ch.key.replace("_rpm", "_sat")] = "hi" if v == 255 else "lo" if v == 0 else ""
            elif ch.kind == "curve":
                t = self.temperature(v, ch.key)
                out[ch.key] = None if t is None else round(t, 1)
                out[ch.raw_key] = v
            elif ch.kind == "hex":
                out[ch.key] = f"{v:02X}"
            elif ch.kind == "bits":
                for b in ch.bits:
                    out[b.key] = int(not (v & b.mask)) if b.active_low else int(bool(v & b.mask))
        if self.ecu == ENGINE and out["boost_kPa"] is not None and out["baro_kPa"] is not None:
            out["boost_gauge_kPa"] = round(out["boost_kPa"] - out["baro_kPa"], 1)
        return out


# ---------------------------------------------------------------------------------------------
# docs
# ---------------------------------------------------------------------------------------------
def channels_markdown(ecu):
    rows = ["| Request | Column | Name | Unit | Formula | Confidence | Evidence |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for ch in BY_ECU[ecu]:
        if ch.kind == "bits":
            rows.append(f"| {ch.addr:02X} | *{ch.key}* | {ch.name} | bits | {ch.formula} | | |")
            for b in ch.bits:
                pol = " (active low)" if b.active_low else ""
                rows.append(f"| {ch.addr:02X} | {b.key} | {b.name}{pol} | 0/1 | mask {b.mask:02X} | "
                            f"{b.confidence} | {b.evidence} |")
        else:
            rows.append(f"| {ch.addr:02X} | {ch.key} | {ch.name} | {ch.unit} | {ch.formula} | "
                        f"{ch.confidence} | {ch.evidence} |")
    return "\n".join(rows)


def channel_meta(ecu):
    """JSON-friendly metadata for the dashboard."""
    out = {}
    for ch in BY_ECU[ecu]:
        if ch.kind == "bits":
            for b in ch.bits:
                out[b.key] = {"name": b.name, "unit": "", "addr": f"{ch.addr:02X}", "confidence": b.confidence,
                              "evidence": b.evidence, "kind": "bit"}
        else:
            for col in ch.columns:
                out[col] = {"name": ch.name if col == ch.key else f"{ch.name} (raw)",
                            "unit": ch.unit if col == ch.key else "raw", "addr": f"{ch.addr:02X}",
                            "confidence": ch.confidence, "evidence": ch.evidence, "kind": ch.kind}
    return out


if __name__ == "__main__":
    import sys
    print(channels_markdown(sys.argv[1] if len(sys.argv) > 1 else GEARBOX))
