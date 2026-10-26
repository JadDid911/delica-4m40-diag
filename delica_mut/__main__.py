"""python -m delica_mut <log|decode|live|ai> ..."""
import importlib
import sys

COMMANDS = {"log": "delica-log", "decode": "delica-decode", "live": "delica-live", "ai": "delica-ai"}

if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
    print("usage: python -m delica_mut {log,decode,live,ai} [options]   (same as the delica-* commands)")
    sys.exit(0 if len(sys.argv) < 2 else 2)
sys.exit(importlib.import_module(f"delica_mut.{sys.argv[1]}").main(sys.argv[2:]))
