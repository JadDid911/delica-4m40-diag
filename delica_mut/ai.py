"""delica-ai: compact Markdown + JSON summary of a log, sized for pasting into an AI chat.

Works from a raw wide CSV (delica-log) or a decoded CSV (delica-decode). Phases, events, trends and
data-quality notes are computed here so the AI reads a few KB instead of a million CSV cells.
"""

import argparse
import bisect
import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from . import ECUS, ENGINE, GEARBOX, __version__
from .channels import COLUMN_ADDR, Decoder, load_tables
from .decode import decode_raw_rows, detect_ecu, is_raw_csv, parse_tz
from .events import SLIP_LOCKED, SLIP_RELOCKED, detect_lockup_releases

BANDS = (0, 30, 50, 70, 90, 110, 1000)
MIN_PHASE_S = 6
TEXT = {"shift_pos", "inhibitor", "marker", "fresh", "time", "dcc_slip_sat"}


# ----------------------------------------------------------------------------------- loading ---
def _num(text):
    if text in ("", None):
        return None
    try:
        return float(text)
    except ValueError:
        return text


def load_rows(path, ecu=None, tz=None, tables=None):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        raw = list(reader)
    if is_raw_csv(header):
        ecu = ecu or detect_ecu(path, header)
        rows = decode_raw_rows(raw, ecu, Decoder(ecu, tables=tables), tz)
    else:
        if "utc_ms" not in header:
            raise SystemExit("need a CSV from delica-log or delica-decode (with a utc_ms column)")
        rows = [{k: (v if k in TEXT else _num(v)) for k, v in r.items()} for r in raw]
        ecu = ecu or (GEARBOX if "dcc_duty_pct" in header or "input_rpm" in header else ENGINE)
    t0 = rows[0]["utc_ms"]
    for r in rows:
        r["t"] = (r["utc_ms"] - t0) / 1000.0
        text = r.get("fresh") or ""
        r["fresh_set"] = {int(x, 16) for x in text.split()} if text else None
    return ecu, rows


class Series:
    """Fresh samples of one decoded column: times, values, with interpolation and age lookups."""

    def __init__(self, rows, col, addr):
        pairs = [(r["t"], r[col]) for r in rows
                 if r.get(col) not in (None, "") and (r["fresh_set"] is None or addr in r["fresh_set"])]
        self.t = [p[0] for p in pairs]
        self.v = [p[1] for p in pairs]

    def __bool__(self):
        return bool(self.t)

    def at(self, t):
        """Linear interpolation for numbers, previous value for text."""
        if not self.t:
            return None
        i = bisect.bisect_right(self.t, t)
        if i == 0:
            return self.v[0]
        if i == len(self.t) or isinstance(self.v[i - 1], str):
            return self.v[i - 1]
        t0, t1, v0, v1 = self.t[i - 1], self.t[i], self.v[i - 1], self.v[i]
        return v0 + (v1 - v0) * (t - t0) / (t1 - t0) if t1 > t0 else v1

    def prev(self, t):
        i = bisect.bisect_right(self.t, t) - 1
        return (self.v[i], round(t - self.t[i], 1)) if i >= 0 else (None, None)

    def next(self, t):
        i = bisect.bisect_left(self.t, t)
        return (self.v[i], round(self.t[i] - t, 1)) if i < len(self.t) else (None, None)

    def window(self, t0, t1):
        lo, hi = bisect.bisect_left(self.t, t0), bisect.bisect_left(self.t, t1)
        return self.v[lo:hi]


def _r(x, n=1):
    return None if x is None else round(x, n)


def _stats(series, t0, t1, n=1):
    vals = [v for v in series.window(t0, t1) if not isinstance(v, str)]
    if not vals:
        mid = series.at((t0 + t1) / 2) if series else None
        vals = [mid] if isinstance(mid, (int, float)) else []
    if not vals:
        return None
    return {"mean": _r(statistics.fmean(vals), n), "min": _r(min(vals), n), "max": _r(max(vals), n)}


def _mode(series, t0, t1):
    vals = series.window(t0, t1) or ([series.prev(t0)[0]] if series else [])
    vals = [v for v in vals if v is not None]
    return Counter(vals).most_common(1)[0][0] if vals else None


# ------------------------------------------------------------------------------------ phases ---
def _band(v):
    for lo, hi in zip(BANDS, BANDS[1:]):
        if lo <= v < hi:
            return f"{lo}-{hi}" if hi < 1000 else f"{lo}+"
    return "?"


def _label(ecu, speed, slope, pedal, rpm, gear, idle_v):
    if rpm is not None and rpm < 250:
        return "engine off"
    if ecu == ENGINE and (speed is None or speed < 2):
        return "idle" if pedal is None or pedal <= idle_v else "revving (parked)"
    if speed is None:
        return "unknown (no speed channel)"
    if speed < 2:
        return "idle" if gear in (None, "N/P") else "stopped"
    if pedal is not None and pedal <= idle_v:
        return "coasting"
    if slope > 1.2:
        return "accelerating"
    if slope < -1.2:
        return "slowing"
    return f"cruise {_band(speed)} km/h"


def _runs(labels):
    runs = []
    for i, lab in enumerate(labels):
        if runs and runs[-1][2] == lab:
            runs[-1][1] = i + 1
        else:
            runs.append([i, i + 1, lab])
    return runs


def phases(ecu, rows, S, duration):
    n = int(duration) + 1
    idle_v = None
    if S["pedal_V"]:
        ordered = sorted(v for v in S["pedal_V"].v)
        idle_v = ordered[int(0.05 * (len(ordered) - 1))] + 0.2
    speed = S["speed_kmh"]
    labels = []
    for k in range(n):
        sp = speed.at(k + .5) if speed else None
        slope = ((speed.at(k + 2.5) - speed.at(k - 1.5)) / 4) if speed else 0
        gear = S["shift_pos"].prev(k + .5)[0] if S.get("shift_pos") else None
        rpm = S["engine_rpm" if ecu == GEARBOX else "rpm"].at(k + .5)
        labels.append(_label(ecu, sp, slope, S["pedal_V"].at(k + .5) if S["pedal_V"] else None, rpm, gear, idle_v or 1.0))
    labels = [Counter(labels[max(0, i - 3):i + 4]).most_common(1)[0][0] for i in range(n)]
    runs = _runs(labels)
    changed = True
    while changed and len(runs) > 1:   # absorb blips shorter than MIN_PHASE_S into their neighbour
        changed = False
        for i, (a, b, lab) in enumerate(runs):
            if b - a < MIN_PHASE_S:
                j = i - 1 if i else i + 1
                runs[j][1 if j < i else 0] = b if j < i else a
                runs.pop(i)
                runs = _runs([r[2] for r in runs for _ in range(r[1] - r[0])])
                changed = True
                break
    return runs


def phase_stats(ecu, runs, S, rows, events):
    out = []
    for a, b, lab in runs:
        d = {"start_s": a, "end_s": b, "duration_s": b - a, "phase": lab}
        d["start_clock"] = _clock(rows, a)
        if ecu == GEARBOX:
            d.update(speed_kmh=_stats(S["speed_kmh"], a, b), engine_rpm=_stats(S["engine_rpm"], a, b, 0),
                     pedal_V=_stats(S["pedal_V"], a, b, 2), gear=_mode(S["shift_pos"], a, b),
                     atf_C=_stats(S["atf_C"], a, b, 0))
            slip = [v for v in S["dcc_slip_rpm"].window(a, b)] if S["dcc_slip_rpm"] else []
            if slip and d["gear"] in ("3rd", "4th"):
                d["locked_share_pct"] = round(100 * sum(v <= SLIP_LOCKED for v in slip) / len(slip))
            d["lockup_releases"] = sum(a <= e["t_s"] < b for e in events if e["type"] == "lockup_release")
        else:
            d.update(speed_kmh=_stats(S["speed_kmh"], a, b, 0), rpm=_stats(S["rpm"], a, b, 0),
                     pedal_V=_stats(S["pedal_V"], a, b, 2), boost_gauge_kPa=_stats(S["boost_gauge_kPa"], a, b),
                     coolant_C=_stats(S["coolant_C"], a, b, 0), battery_V=_stats(S["battery_V"], a, b, 2))
            for name, (x, y) in {"timing_error_CA": ("timing_actual_CA", "timing_target_CA"),
                                 "sleeve_error_pct": ("sleeve_actual_pct", "sleeve_target_pct")}.items():
                xa, ya = S[x].window(a, b), S[y].window(a, b)
                if xa and ya:
                    d[name] = round(statistics.fmean(abs(p - q) for p, q in zip(xa, ya)), 1)
        out.append(d)
    return out


def _clock(rows, t):
    times = [r["t"] for r in rows]
    return rows[max(bisect.bisect_right(times, t) - 1, 0)]["time"][:8]


# ------------------------------------------------------------------------------------ events ---
def lockup_events(S, rows):
    slip = S["dcc_slip_rpm"]
    if not slip:
        return []
    inputs = [S["input_rpm"].at(t) if S["input_rpm"] else None for t in slip.t]
    gears = [S["shift_pos"].prev(t)[0] if S["shift_pos"] else None for t in slip.t]
    return [_lockup_event(S, slip, j, i) for j, i, _ in detect_lockup_releases(slip.t, slip.v, inputs, gears)]


def _lockup_event(S, slip, j, i):
    t = slip.t[j]                       # first sample that left the locked state
    end = next((slip.t[k] for k in range(i, len(slip.t)) if slip.v[k] <= SLIP_RELOCKED), None)
    pedal = S["pedal_V"]
    ped_now = pedal.at(t)
    before = [v for v in pedal.window(t - 5, t - 0.5)]
    ped_before = statistics.fmean(before) if before else None
    sp, sp_age = S["speed_kmh"].prev(t) if S["speed_kmh"] else (None, None)
    spn, spn_age = S["speed_kmh"].next(t) if S["speed_kmh"] else (None, None)
    speed = S["speed_kmh"].at(t) if S["speed_kmh"] else None
    gear, gear_age = S["shift_pos"].prev(t) if S["shift_pos"] else (None, None)
    gear_change = bool(S["shift_pos"]) and len(set(S["shift_pos"].window(t - 3, t + 3))) > 1
    in_before = statistics.fmean(S["input_rpm"].window(t - 1.5, t - 0.5) or [0])
    in_after = statistics.fmean(S["input_rpm"].window(t + 1.0, t + 2.5) or [0])
    in_step = 100 * (in_after - in_before) / in_before if in_before > 300 and in_after else 0
    duty_b, duty_b_age = S["dcc_duty_pct"].prev(t) if S["dcc_duty_pct"] else (None, None)
    duty_a, duty_a_age = S["dcc_duty_pct"].next(t + 0.5) if S["dcc_duty_pct"] else (None, None)   # the duty ramps down over ~0.5 s
    duty_a_age = None if duty_a_age is None else round(duty_a_age + 0.5, 1)
    idle_v, idle_age = S["idle_pos"].prev(t) if S["idle_pos"] else (None, None)
    brake, brake_age = S["brake"].prev(t) if S["brake"] else (None, None)
    peak = max(slip.window(t, end or t + 10) or [slip.v[i]])
    ev = {
        "type": "lockup_release", "t_s": round(t, 1), "pedal_V": _r(ped_now, 2), "pedal_V_5s_before": _r(ped_before, 2),
        "speed_kmh": _r(speed), "speed_age_s": min((x for x in (sp_age, spn_age) if x is not None), default=None),
        "gear": gear, "gear_age_s": gear_age, "engine_rpm": _r(S["engine_rpm"].at(t + 0.5), 0) if S["engine_rpm"] else None,
        "input_rpm": _r(S["input_rpm"].at(t), 0) if S["input_rpm"] else None, "peak_slip_rpm": peak,
        "slip_saturated": bool(peak >= 204), "input_rpm_step_pct": _r(in_step),
        "released_for_s": _r(end - t, 1) if end else None,
        "relock_pedal_V": _r(pedal.at(end), 2) if end else None,
        "dcc_duty_before_pct": duty_b, "dcc_duty_before_age_s": duty_b_age,
        "dcc_duty_after_pct": duty_a, "dcc_duty_after_age_s": duty_a_age,
        "idle_flag": idle_v, "idle_flag_age_s": idle_age, "brake": brake, "brake_age_s": brake_age,
    }
    ev["duty_confirms_release"] = bool(duty_b is not None and duty_a is not None and duty_b >= 50 and duty_a <= 25)
    idle_now = idle_v == 1 and idle_age is not None and idle_age <= 1.5   # the flag can be seconds old
    lifted = (ped_now is not None and ped_now <= (pedal.at(t - 2) or 0) - 0.1) or idle_now
    rose = ped_before is not None and ped_now is not None and ped_now - ped_before
    if gear_change or abs(in_step) >= 8:
        hint = "input rpm or gear changed around the release (normal release around a shift)"
    elif lifted:
        hint = "pedal lifted / idle flag set (coast or lift-off release)"
    elif in_step >= 3 and rose and rose >= 0.15:
        hint = "accelerating (kick-down or load release)"
    elif rose and rose >= 0.05 and abs(in_step) < 5:
        hint = "pedal rose at steady input speed (possible lock-up schedule release; compare relock pedal V)"
    else:
        hint = "no clear cause in the logged channels"
    ev["kind"] = "full release" if peak >= 190 else "partial slip"
    if ev["kind"] == "partial slip" and hint.startswith("no clear"):
        hint = "partial slip only (controlled slip at moderate throttle; DCC duty about 30-40 % is normal there)"
    ev["cause_hint"] = hint
    return ev


def marker_events(rows, S, ecu):
    out, last = [], None
    for r in rows:
        m = r.get("marker")
        if m and m != last and m != "start":
            t = r["t"]
            snap = {k: _r(S[k].at(t), 2) if S[k] and not isinstance(S[k].at(t), str) else (S[k].at(t) if S[k] else None)
                    for k in (("pedal_V", "engine_rpm", "speed_kmh") if ecu == GEARBOX else ("pedal_V", "rpm", "boost_gauge_kPa"))}
            out.append({"type": "marker", "t_s": round(t, 1), "label": m, **snap})
        last = m
    return out


def engine_events(S, rows):
    """Idle rpm dips (rough idle) and non-zero fault bytes."""
    events, rpm, pedal = [], S["rpm"], S["pedal_V"]
    if rpm and pedal:
        idle_v = sorted(pedal.v)[int(0.05 * (len(pedal.v) - 1))] + 0.2
        idle = [(t, v) for t, v in zip(rpm.t, rpm.v) if pedal.at(t) <= idle_v and v > 400]
        if len(idle) > 20:
            base = statistics.median(v for _, v in idle)
            i = 0
            while i < len(idle):
                if idle[i][1] <= base - 75:
                    j = i
                    while j + 1 < len(idle) and idle[j + 1][1] <= base - 75:
                        j += 1
                    t = idle[i][0]
                    events.append({"type": "idle_rpm_dip", "t_s": round(t, 1), "rpm_min": min(v for _, v in idle[i:j + 1]),
                                   "idle_median_rpm": base, "duration_s": round(idle[j][0] - t, 1),
                                   "idle_sw1": S["idle_sw1"].prev(t)[0] if S["idle_sw1"] else None,
                                   "idle_sw2": S["idle_sw2"].prev(t)[0] if S["idle_sw2"] else None,
                                   "timing_actual_minus_target_CA": _r((S["timing_actual_CA"].at(t) or 0) - (S["timing_target_CA"].at(t) or 0), 1)
                                   if S["timing_actual_CA"] and S["timing_target_CA"] else None})
                    i = j + 1
                else:
                    i += 1
    faults = {}
    for key in ("fault_50", "fault_51", "fault_52", "fault_53") if S.ecu == ENGINE else ():
        seen = sorted({v for v in S[key].v if v not in ("00", "FF")}) if S[key] else []
        if seen:
            faults[key[-2:]] = seen
    if faults:
        events.append({"type": "fault_bytes_set", "t_s": 0, "bytes": faults,
                       "note": "raw bytes only; look the bits up in your service manual (docs/CHANNELS.md)"})
    return events


def gearbox_fault_event(S):
    seen = {k[-2:]: sorted({v for v in S[k].v if v not in ("00", "FF")}) for k in S.cols if k.startswith("fault_") and S[k]}
    seen = {k: v for k, v in seen.items() if v}
    return [{"type": "fault_bytes_set", "t_s": 0, "bytes": seen, "note": "raw bytes only; no descriptions shipped"}] if seen else []


# -------------------------------------------------------------------------------- quality ------
def data_quality(ecu, rows, S, duration):
    dt = [b["t"] - a["t"] for a, b in zip(rows, rows[1:]) if b["t"] > a["t"]]
    quality = {"rows": len(rows), "duration_s": round(duration, 1),
               "rows_per_s": round(len(rows) / duration, 2) if duration else None,
               "median_row_gap_s": _r(statistics.median(dt), 3) if dt else None,
               "max_row_gap_s": _r(max(dt), 1) if dt else None, "channels": {}, "notes": []}
    for col, series in S.items():
        if not series or col not in COLUMN_ADDR[ecu] or col.endswith(("_raw", "_sat")):
            continue
        gaps = [b - a for a, b in zip(series.t, series.t[1:])]
        quality["channels"][col] = {"fresh_samples": len(series.t),
                                    "median_interval_s": _r(statistics.median(gaps), 2) if gaps else None}
    slow = sorted(c for c, q in quality["channels"].items() if (q["median_interval_s"] or 0) > 2)
    fast = sorted(c for c, q in quality["channels"].items() if (q["median_interval_s"] or 0) <= 2)
    if slow:
        age = max(quality["channels"][c]["median_interval_s"] for c in slow)
        names = ", ".join(slow[:6]) + (f" and {len(slow) - 6} more" if len(slow) > 6 else "")
        quality["notes"].append(
            f"{len(slow)} slow channels ({names}) were refreshed only every ~{age:g} s; between refreshes the CSV repeats "
            "the last value. Speed, gear, DCC duty and flag values at an event can be that stale (see *_age_s).")
    if fast:
        quality["notes"].append(f"Fast channels ({', '.join(fast[:8])}) were refreshed every cycle, about "
                                f"{_r(1 / statistics.median(dt), 1) if dt else '?'} Hz.")
    if ecu == GEARBOX and S["dcc_slip_sat"]:
        sat = Counter(S["dcc_slip_sat"].v)
        total = len(S["dcc_slip_sat"].v)
        quality["slip_saturated_pct"] = {"hi": round(100 * sat["hi"] / total, 1), "lo": round(100 * sat["lo"] / total, 1)}
        quality["notes"].append("DCC slip saturates at raw 0 and 255 (204 rpm shown): treat those samples as 'at least', not exact.")
    if quality["max_row_gap_s"] and quality["max_row_gap_s"] > 2:
        quality["notes"].append(f"Largest gap between rows was {quality['max_row_gap_s']} s (logging stall).")
    missing = [c for c in ("speed_kmh", "shift_pos", "dcc_duty_pct") if ecu == GEARBOX and not S[c]]
    if missing:
        quality["notes"].append(f"Not in this log: {', '.join(missing)}; phases and event context are weaker.")
    return quality


def trends(ecu, S, duration):
    out = {}
    cols = ("atf_C",) if ecu == GEARBOX else ("coolant_C", "boost_air_C", "fuel_C", "battery_V")
    for col in cols:
        s = S[col]
        if len(s.t) >= 2:
            first = statistics.fmean(s.v[:max(1, len(s.v) // 20)])
            last = statistics.fmean(s.v[-max(1, len(s.v) // 20):])
            out[col] = {"start": _r(first), "end": _r(last), "min": _r(min(s.v)), "max": _r(max(s.v)),
                        "change_per_10min": _r((last - first) * 600 / duration) if duration else None}
    return out


# ---------------------------------------------------------------------------------- assemble ---
class Cols(dict):
    ecu = None

    def __missing__(self, key):
        return Series([], key, 0)


def summarize(path, ecu=None, tz=None, tables=None):
    ecu, rows = load_rows(path, ecu, tz, tables)
    duration = rows[-1]["t"]
    S = Cols()
    S.ecu = ecu
    S.cols = [c for c in COLUMN_ADDR[ecu]]
    for col, addr in COLUMN_ADDR[ecu].items():
        S[col] = Series(rows, col, addr)
    if ecu == ENGINE:   # derived column has no request of its own: use baro/boost freshness
        S["boost_gauge_kPa"] = Series(rows, "boost_gauge_kPa", COLUMN_ADDR[ecu]["boost_kPa"])
    events = lockup_events(S, rows) if ecu == GEARBOX else engine_events(S, rows)
    events += (gearbox_fault_event(S) if ecu == GEARBOX else []) + marker_events(rows, S, ecu)
    events.sort(key=lambda e: e["t_s"])
    runs = phases(ecu, rows, S, duration)
    for e in events:
        e["clock"] = _clock(rows, e["t_s"])
    summary = {
        "tool": "delica-4m40-diag", "version": __version__, "ecu": ecu, "source": Path(path).name,
        "start_clock": rows[0]["time"][:8], "end_clock": rows[-1]["time"][:8],
        "phases": phase_stats(ecu, runs, S, rows, events), "events": events,
        "trends": trends(ecu, S, duration), "data_quality": data_quality(ecu, rows, S, duration),
    }
    if ecu == ENGINE:
        summary["temperature_note"] = ("Engine temperature channels are provisional (Steinhart-Hart curve, about +/-3 C, "
                                       "independent calibration pending) unless the user supplied tables.")
        top = S["boost_gauge_kPa"]
        if top:
            summary["peaks"] = {"rpm_max": max(S["rpm"].v) if S["rpm"] else None, "boost_gauge_kPa_max": _r(max(top.v)),
                                "pedal_V_max": _r(max(S["pedal_V"].v), 2) if S["pedal_V"] else None}
    return summary


# ------------------------------------------------------------------------------------ output ---
def _tzlabel(tz):
    if tz in (None, "", "local"):
        return "local time of the machine that made this summary"
    return "UTC" if str(tz).lower() == "utc" else f"UTC{'+' if not str(tz).startswith('-') else ''}{tz}"


def _rng(d):
    return f"{d['mean']} ({d['min']}-{d['max']})" if d else "n/a"


def _fmt(d, *keys):
    if not d:
        return "n/a"
    return "/".join(str(d[k]) for k in keys)


def to_markdown(s, max_events=25):
    ecu = "gearbox F3 06" if s["ecu"] == GEARBOX else "engine 3002"
    q = s["data_quality"]
    lines = [f"# Delica 4M40 log summary: {ecu}", "",
             f"Source `{s['source']}`, {q['rows']} rows, {q['duration_s']:g} s, clock {s['start_clock']} to {s['end_clock']} ({_tzlabel(s.get('timezone'))}). "
             f"Made by delica-4m40-diag {s['version']}. Values are decoded from raw ECU bytes; confidence per channel is in docs/CHANNELS.md.", ""]
    lines += ["## Drive phases", ""]
    if s["ecu"] == GEARBOX:
        lines += ["| start | dur s | phase | speed km/h mean (min-max) | engine rpm mean | pedal V mean (min-max) | gear | locked % | releases | ATF C |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for p in s["phases"]:
            lines.append(f"| {p['start_clock']} | {p['duration_s']} | {p['phase']} | {_rng(p.get('speed_kmh'))} | "
                         f"{_fmt(p.get('engine_rpm'), 'mean')} | {_rng(p.get('pedal_V'))} | {p.get('gear') or 'n/a'} | "
                         f"{p.get('locked_share_pct', '')} | {p.get('lockup_releases') or ''} | {_fmt(p.get('atf_C'), 'mean')} |")
    else:
        lines += ["| start | dur s | phase | rpm mean (max) | pedal V mean (max) | boost gauge kPa (max) | timing err CA | sleeve err % | coolant C |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for p in s["phases"]:
            lines.append(f"| {p['start_clock']} | {p['duration_s']} | {p['phase']} | "
                         f"{_fmt(p.get('rpm'), 'mean')} ({_fmt(p.get('rpm'), 'max')}) | "
                         f"{_fmt(p.get('pedal_V'), 'mean')} ({_fmt(p.get('pedal_V'), 'max')}) | "
                         f"{_fmt(p.get('boost_gauge_kPa'), 'mean')} ({_fmt(p.get('boost_gauge_kPa'), 'max')}) | "
                         f"{p.get('timing_error_CA', 'n/a')} | {p.get('sleeve_error_pct', 'n/a')} | {_fmt(p.get('coolant_C'), 'mean')} |")
    rel = [e for e in s["events"] if e["type"] == "lockup_release"]
    if rel:
        lines += ["", f"## Lock-up releases ({len(rel)})", "",
                  "Release = DCC slip jumps from locked (<=40 rpm) to >=100 rpm (full release = peak slip >=190 rpm, otherwise partial slip). Pedal V is the value at the release; `-5s` is the mean of the 5 s before.", "",
                  "| time | kind | pedal V (-5s) | speed km/h | gear | engine/input rpm | peak slip | released s | relock pedal V | DCC duty before>after | idle flag | brake | hint |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for e in rel[:max_events]:
            lines.append(
                f"| {e['clock']} | {e['kind']} | {e['pedal_V']} ({e['pedal_V_5s_before']}) | {e['speed_kmh']} (age {e['speed_age_s']} s) | "
                f"{e['gear']} (age {e['gear_age_s']} s) | {e['engine_rpm']}/{e['input_rpm']} | "
                f"{'>=' if e['slip_saturated'] else ''}{e['peak_slip_rpm']} | {e['released_for_s']} | {e['relock_pedal_V']} | "
                f"{e['dcc_duty_before_pct']}>{e['dcc_duty_after_pct']} | {e['idle_flag']} | {e['brake']} | {e['cause_hint']} |")
        if len(rel) > max_events:
            lines.append(f"\n({len(rel) - max_events} more in the JSON.)")
    other = [e for e in s["events"] if e["type"] not in ("lockup_release",)]
    if other:
        lines += ["", "## Other events", ""]
        for e in other[:max_events]:
            body = ", ".join(f"{k}={v}" for k, v in e.items() if k not in ("type", "t_s", "clock"))
            lines.append(f"- {e['clock']} {e['type']}: {body}")
    if s["trends"]:
        lines += ["", "## Trends", ""]
        for col, t in s["trends"].items():
            lines.append(f"- {col}: {t['start']} -> {t['end']} (min {t['min']}, max {t['max']}, {t['change_per_10min']} per 10 min)")
    if s.get("temperature_note"):
        lines += ["", s["temperature_note"]]
    lines += ["", "## Data quality", ""]
    lines += [f"- {n}" for n in q["notes"]]
    lines.append(f"- {q['rows_per_s']} rows/s, median row gap {q['median_row_gap_s']} s, largest {q['max_row_gap_s']} s.")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="delica-ai", description=__doc__)
    ap.add_argument("input", help="raw (delica-log) or decoded (delica-decode) CSV")
    ap.add_argument("-o", "--output", help="output prefix (default: <input>.ai-summary): writes .md and .json")
    ap.add_argument("--ecu", choices=ECUS)
    ap.add_argument("--tz-offset", help="hours from UTC for clock times (default: this machine's zone)")
    ap.add_argument("--temp-tables", help="your own temperature tables JSON (engine logs)")
    ap.add_argument("--stdout", action="store_true", help="print the Markdown instead of writing files")
    a = ap.parse_args(argv)
    summary = summarize(a.input, a.ecu, parse_tz(a.tz_offset), load_tables(a.temp_tables))
    summary["timezone"] = a.tz_offset or "local"
    md = to_markdown(summary)
    if a.stdout:
        print(md)
        return 0
    prefix = a.output or str(Path(a.input).with_suffix("")) + ".ai-summary"
    Path(prefix + ".md").write_text(md, encoding="utf-8")
    Path(prefix + ".json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(f"wrote {prefix}.md ({len(md)} chars) and {prefix}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
