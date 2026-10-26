"""delica-log: record a gearbox (F3 06) or engine (3002) session to a wide CSV + JSONL events."""

import argparse
import sys
import threading

from . import ECUS, ENGINE, GEARBOX
from .recorder import PROFILES, EventLog, Recorder, default_paths, profiles_for
from .sessions import SessionLost, WakeError, open_session

BANNER = """Read-only logger. Check before you start:
  - DLC pin 1 grounded (diagnosis mode), pin 7 = K-line to the cable. NEVER connect pin 9.
  - Both computers share pin 7: log one at a time. Park the van for the wake-up.
  - Type a label + Enter to mark an event, 'q' + Enter to stop."""


def open_cli_session(ecu, args, log):
    if not args.sim:
        quiet = "10 s quiet line" if ecu == ENGINE else "1.5 s quiet line"
        print(f"Opening the cable, then waking the {ecu} computer ({quiet}, then the 5-baud address)...", flush=True)
    return open_session(ecu, log, sim=args.sim, port=args.port, ftdi_serial=args.ftdi_serial, raw_bytes=args.raw_log)


def stdin_markers(rec):
    def run():
        for line in sys.stdin:
            line = line.strip()
            if line.lower() in ("q", "quit", "stop"):
                rec.stop("user stop")
                return
            if line:
                rec.mark(line)
                print(f"MARK {line}", flush=True)
    threading.Thread(target=run, daemon=True).start()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="delica-log", description=__doc__, epilog=BANNER,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ecu", choices=ECUS, default=GEARBOX)
    ap.add_argument("--profile", choices=list(PROFILES), help="default: gearbox-cruise or engine")
    ap.add_argument("--seconds", type=float, default=900)
    ap.add_argument("--out", default="logs", help="output folder (default ./logs)")
    ap.add_argument("--port", help="serial port, e.g. COM5 or /dev/ttyUSB0 (default: first cable found)")
    ap.add_argument("--ftdi-serial", help="FTDI serial number for the Windows D2XX driver")
    ap.add_argument("--rewake", type=int, default=0, metavar="N",
                    help="explicitly allow up to N automatic re-wakes after a dropped session (default 0 = stop)")
    ap.add_argument("--raw-log", action="store_true", help="also log every TX/RX byte (large)")
    ap.add_argument("--sim", action="store_true", help="use the built-in ECU simulator, no hardware")
    a = ap.parse_args(argv)
    profile = a.profile or ("engine" if a.ecu == ENGINE else "gearbox-cruise")
    if profile not in profiles_for(a.ecu):
        ap.error(f"profile {profile} is not for the {a.ecu} computer ({', '.join(profiles_for(a.ecu))})")
    if not 1 <= a.seconds <= 14400:
        ap.error("--seconds must be 1..14400")

    print(BANNER)
    csv_path, events_path = default_paths(a.out, a.ecu, profile)
    events = EventLog(events_path)
    cleanup = lambda: None
    try:
        session, wake, cleanup = open_cli_session(a.ecu, a, events)
        rec = Recorder(session, profile, log=events, wake=wake, max_rewakes=a.rewake,
                       on_row=lambda r: print(f"\rcycle {r.cycle}  t={r.elapsed_s:7.1f}s", end="", flush=True) if r.cycle % 25 == 0 else None)
        rec.start_csv(csv_path)
        print(f"{a.ecu} session OK (ID {session.ecu_id}). Recording {profile} to {csv_path}", flush=True)
        stdin_markers(rec)
        result = rec.run(a.seconds)
    except (WakeError, SessionLost) as exc:
        print(f"\nStopped: {exc}", file=sys.stderr)
        events.ev("run_aborted", error=str(exc))
        return 2
    except (OSError, RuntimeError) as exc:   # cable missing, port busy, driver error
        print(f"\nCould not use the cable: {exc}", file=sys.stderr)
        events.ev("run_aborted", error=str(exc))
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted; files are saved.")
        return 130
    finally:
        cleanup()
        events.close()
    print(f"\nDone: {result['cycles']} cycles, {result['reason']}\n  {csv_path}\n  {events_path}")
    return 0 if result["reason"] in ("duration reached", "user stop", "stop requested") else 3


if __name__ == "__main__":
    sys.exit(main())
