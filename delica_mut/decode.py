"""delica-decode: raw wide CSV (rXX columns) -> engineering units."""

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

from . import ECUS, ENGINE, GEARBOX
from .channels import BY_ECU, Decoder, columns, load_tables
from .safety import ENGINE_READS, ENGINE_ROM_ID_READS

META = ["time", "utc_ms", "elapsed_s", "marker"]


def parse_tz(text):
    """None -> this machine's local zone; 'utc'; or a whole/fractional hour offset such as -5 or 5.5."""
    if text in (None, "", "local"):
        return None
    if str(text).lower() == "utc":
        return dt.timezone.utc
    return dt.timezone(dt.timedelta(hours=float(text)))


def clock_text(utc_ms, tz):
    stamp = dt.datetime.fromtimestamp(int(utc_ms) / 1000, tz)
    return stamp.strftime("%H:%M:%S.%f")[:10]


def raw_ids(header):
    ids = []
    for name in header:
        if len(name) == 3 and name[0] == "r":
            try:
                ids.append(int(name[1:], 16))
            except ValueError:
                pass
    return ids


def is_raw_csv(header):
    return "utc_ms" in header and bool(raw_ids(header))


def detect_ecu(path, header):
    """Sidecar events file first (written by delica-log), then the request ids present."""
    sidecar = Path(path).with_suffix(".events.jsonl")
    if sidecar.is_file():
        try:
            first = json.loads(sidecar.read_text(encoding="utf-8").splitlines()[0])
            if first.get("ecu") in ECUS:
                return first["ecu"]
            for line in sidecar.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                if rec.get("ev") == "run_start" and rec.get("ecu") in ECUS:
                    return rec["ecu"]
        except (ValueError, IndexError):
            pass
    allowed = ENGINE_READS | set(ENGINE_ROM_ID_READS)
    return GEARBOX if any(i not in allowed for i in raw_ids(header)) else ENGINE


def decode_raw_rows(rows, ecu, decoder=None, tz=None):
    decoder = decoder or Decoder(ecu)
    out = []
    for r in rows:
        raw = {int(k[1:], 16): int(v) for k, v in r.items() if k.startswith("r") and len(k) == 3 and v not in ("", None)}
        d = {"time": clock_text(r["utc_ms"], tz), "utc_ms": int(r["utc_ms"]), "elapsed_s": float(r["elapsed_s"]),
             "marker": r.get("marker", "")}
        d.update(decoder.decode(raw))
        d["fresh"] = r.get("fresh", "")
        out.append(d)
    return out


def decoded_columns(ecu):
    return META + columns(ecu) + ["fresh"]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="delica-decode", description=__doc__)
    ap.add_argument("input", help="raw wide CSV written by delica-log")
    ap.add_argument("-o", "--output", help="decoded CSV (default: <input>.decoded.csv)")
    ap.add_argument("--ecu", choices=ECUS, help="default: detected from the events file or the columns")
    ap.add_argument("--raw-temps", action="store_true",
                    help="engine: leave the temperature columns empty and keep only the raw bytes")
    ap.add_argument("--temp-tables", help="JSON with your own 256-entry temperature tables (see docs/CHANNELS.md)")
    ap.add_argument("--tz-offset", help="hours from UTC for the time column (default: this machine's zone)")
    a = ap.parse_args(argv)

    with open(a.input, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        header = reader.fieldnames or []
    if not is_raw_csv(header):
        ap.error("input does not look like a raw delica-log CSV (needs utc_ms and rXX columns)")
    ecu = a.ecu or detect_ecu(a.input, header)
    decoder = Decoder(ecu, tables=load_tables(a.temp_tables), raw_temps=a.raw_temps)
    decoded = decode_raw_rows(rows, ecu, decoder, parse_tz(a.tz_offset))
    out = a.output or str(Path(a.input).with_suffix("")) + ".decoded.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=decoded_columns(ecu))
        w.writeheader()
        w.writerows(decoded)
    print(f"wrote {out}: {len(decoded)} rows ({ecu})")
    if ecu == ENGINE:
        names = [c.key for c in BY_ECU[ENGINE] if c.kind == "curve"]
        print(f"temperature columns {', '.join(names)}: {decoder.temperature_source(names[0])}"
              + (" (calibration pending)" if not decoder.tables and not a.raw_temps else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
