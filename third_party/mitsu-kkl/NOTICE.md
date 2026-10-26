# mitsu-kkl (vendored)

`delica_mut/_vendor/kkl/` is a trimmed copy of the `kkl/` package from **mitsu-kkl**
by Alb7C4 (MIT licence, copyright 2026 Alb7C4). The licence text is in `LICENSE` next to this file
and is repeated inside the vendored folder.

What it gives this project: the FTDI D2XX ctypes wrapper, the pyserial fallback backend, the
K-line link layer (`KLine`: echo-aware TX, UART-break based 5-baud address, timestamped RX) and the
slow-init capture helper.

Changes made for delica-4m40-diag:

- `proto.py` reduced to the 5-baud capture helper (`_slow_init`, `_base_outcome`, `_hex`, `_ms`).
  The other probe strategies (ISO 9141, KWP fast init, DSM) and the DTC-clear helper were removed
  because this project is strictly read-only.
- `interfaces.py`: the simulator branch was removed (the simulator module is not vendored; this
  project has its own ECU-level simulator).
- A UTF-8 byte-order mark was stripped from the start of some files.

Everything else is unmodified. Thank you to the mitsu-kkl author for the transport work.
