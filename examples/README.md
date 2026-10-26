# Sample data

`drive1_gearbox.csv` is about 10 minutes (3,157 cycles, 18:03:00 to 18:12:59, local time of the van) of **gearbox** (F3 06)
data from the first drive of the test van, trimmed from a longer recording. Only the 26 requests of the documented gearbox
channel map are kept; the `fresh` column lists the requests actually read in each cycle. It contains no serial numbers, paths
or other identifying information.

| File | What |
| --- | --- |
| `drive1_gearbox.csv` | raw wide CSV as written by `delica-log` |
| `drive1_gearbox.decoded.csv` | `delica-decode examples/drive1_gearbox.csv --tz-offset -5` |
| `drive1_gearbox.ai-summary.md` / `.json` | `delica-ai examples/drive1_gearbox.csv --tz-offset -5` |

The lock-up release at 18:06:56 (pedal 2.31 V, about 87 km/h, 4th gear) is described in
[docs/FINDINGS-EXAMPLE.md](../docs/FINDINGS-EXAMPLE.md) and is checked by the tests.

In this recording speed, gear and lock-up duty were refreshed only about every 8.7 s (an older profile); the current
`gearbox-cruise` profile reads them every cycle.
