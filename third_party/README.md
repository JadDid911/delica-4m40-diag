# Third-party notices

| Component | Where | Licence | Notes |
| --- | --- | --- | --- |
| mitsu-kkl `kkl/` package | `delica_mut/_vendor/kkl/` | MIT (Alb7C4) | See `mitsu-kkl/NOTICE.md` and `mitsu-kkl/LICENSE` |
| pyserial | runtime dependency (not vendored) | BSD-3-Clause | installed from PyPI |

## Not included on purpose

- **MMC-Reader** database files, raw tables, lookup tables and fault-description texts. This project
  is not affiliated with MMC-Reader. Channel names and scales in this repository were cross-checked
  against the MMC-Reader diagnostic database and then compared with recordings from a real van; only
  the resulting facts (address, name, unit, scale) are published here. See `docs/CHANNELS.md`.
- Multitronics, EvoScan or any other vendor firmware or data files.

The dashboard draws its charts with plain canvas code written for this project; no chart library
and no CDN are used.
