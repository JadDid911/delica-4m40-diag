# Delica 4M40 log summary: gearbox F3 06

Source `drive1_gearbox.csv`, 3157 rows, 599.8 s, clock 18:03:00 to 18:12:59 (UTC-5). Made by delica-4m40-diag 0.1.0. Values are decoded from raw ECU bytes; confidence per channel is in docs/CHANNELS.md.

## Drive phases

| start | dur s | phase | speed km/h mean (min-max) | engine rpm mean | pedal V mean (min-max) | gear | locked % | releases | ATF C |
|---|---|---|---|---|---|---|---|---|---|
| 18:03:00 | 20 | idle | 0.0 (0.0-0.0) | 765.0 | 0.88 (0.86-0.9) | N/P |  |  | 62.0 |
| 18:03:20 | 17 | stopped | 0.0 (0.0-0.0) | 779.0 | 0.88 (0.86-0.9) | R |  |  | 62.0 |
| 18:03:37 | 13 | coasting | 2.8 (2.8-2.8) | 751.0 | 0.88 (0.86-0.92) | R |  |  | 62.0 |
| 18:03:49 | 39 | cruise 0-30 km/h | 14.0 (11.2-19.6) | 1147.0 | 1.18 (0.86-1.48) | 1st |  |  | 62.0 |
| 18:04:29 | 15 | coasting | 7.0 (0.0-14.0) | 808.0 | 0.91 (0.86-1.56) | 2nd |  |  | 63.0 |
| 18:04:43 | 13 | accelerating | 28.0 (14.0-42.0) | 1644.0 | 1.76 (0.96-1.93) | 1st |  |  | 63.0 |
| 18:04:57 | 16 | coasting | 25.2 (25.2-25.2) | 943.0 | 0.89 (0.86-0.92) | 3rd | 48 |  | 63.0 |
| 18:05:13 | 29 | stopped | 0.0 (0.0-0.0) | 750.0 | 0.88 (0.86-0.92) | 1st |  |  | 63.0 |
| 18:05:42 | 24 | accelerating | 46.2 (33.6-58.8) | 2102.0 | 2.33 (0.88-2.64) | 2nd |  |  | 64.0 |
| 18:06:06 | 91 | cruise 70-90 km/h | 83.2 (72.8-89.6) | 2097.0 | 1.97 (0.88-2.34) | 4th | 55 | 3 | 66.0 |
| 18:07:36 | 9 | coasting | 86.8 (86.8-86.8) | 1682.0 | 0.95 (0.86-1.56) | 4th | 100 |  | 67.0 |
| 18:07:45 | 56 | cruise 70-90 km/h | 84.0 (81.2-86.8) | 2037.0 | 1.69 (0.88-1.99) | 4th | 83 | 2 | 67.0 |
| 18:08:42 | 51 | coasting | 56.5 (14.0-81.2) | 1220.0 | 0.98 (0.86-1.62) | 4th | 74 | 1 | 66.0 |
| 18:09:32 | 25 | accelerating | 42.0 (19.6-61.6) | 2012.0 | 2.15 (1.6-2.36) | 4th | 0 |  | 65.0 |
| 18:09:58 | 45 | cruise 70-90 km/h | 77.5 (70.0-81.2) | 1898.0 | 1.6 (0.86-2.31) | 4th | 60 | 2 | 66.0 |
| 18:10:43 | 24 | coasting | 32.2 (11.2-53.2) | 1008.0 | 0.9 (0.86-1.66) | 4th | 56 |  | 66.0 |
| 18:11:06 | 36 | stopped | 0.0 (0.0-0.0) | 756.0 | 0.89 (0.86-1.91) | 1st |  |  | 65.0 |
| 18:11:42 | 13 | accelerating | 23.8 (5.6-42.0) | 1801.0 | 1.96 (1.33-2.21) | 3rd | 0 |  | 65.0 |
| 18:11:56 | 21 | cruise 30-50 km/h | 49.0 (47.6-50.4) | 1277.0 | 1.23 (0.86-1.7) | 4th | 39 | 3 | 66.0 |
| 18:12:17 | 13 | coasting | 36.4 (25.2-47.6) | 995.0 | 0.95 (0.86-1.31) | 3rd | 74 | 1 | 66.0 |
| 18:12:30 | 13 | cruise 0-30 km/h | 25.2 (25.2-25.2) | 1693.0 | 1.83 (1.23-1.93) | 2nd |  |  | 66.0 |
| 18:12:43 | 17 | cruise 30-50 km/h | 32.2 (30.8-33.6) | 1641.0 | 1.7 (1.43-1.88) | 3rd | 0 |  | 66.0 |

## Lock-up releases (12)

Release = DCC slip jumps from locked (<=40 rpm) to >=100 rpm (full release = peak slip >=190 rpm, otherwise partial slip). Pedal V is the value at the release; `-5s` is the mean of the 5 s before.

| time | kind | pedal V (-5s) | speed km/h | gear | engine/input rpm | peak slip | released s | relock pedal V | DCC duty before>after | idle flag | brake | hint |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 18:06:56 | full release | 2.31 (2.22) | 86.8 (age 2.5 s) | 4th (age 8.1 s) | 2300.0/2070.0 | >=204 | 6.1 | 2.13 | 98.8>0.0 | 0 | 0 | pedal rose at steady input speed (possible lock-up schedule release; compare relock pedal V) |
| 18:07:24 | partial slip | 1.52 (1.55) | 81.3 (age 0.2 s) | 4th (age 1.8 s) | 2064.0/2010.0 | 149 | 3.7 | 1.66 | 0.0>34.5 | 1 | 0 | pedal lifted / idle flag set (coast or lift-off release) |
| 18:07:29 | partial slip | 1.7 (1.56) | 82.8 (age 3.7 s) | 4th (age 6.7 s) | 2150.0/1980.0 | 172 | 4.1 | 1.8 | 0.0>34.5 | 1 | 0 | pedal rose at steady input speed (possible lock-up schedule release; compare relock pedal V) |
| 18:07:47 | partial slip | 1.5 (1.03) | 84.9 (age 2.9 s) | 4th (age 7.6 s) | 2100.0/2040.0 | 158 | 3.1 | 1.7 | 0.0>31.4 | 1 | 0 | pedal rose at steady input speed (possible lock-up schedule release; compare relock pedal V) |
| 18:08:02 | partial slip | 1.64 (1.45) | 84.4 (age 3.6 s) | 4th (age 5.5 s) | 2100.0/2010.0 | 144 | 3.7 | 1.78 | 35.7>38.4 | 0 | 0 | pedal rose at steady input speed (possible lock-up schedule release; compare relock pedal V) |
| 18:08:51 | partial slip | 1.52 (1.12) | 72.7 (age 0.4 s) | 4th (age 2.3 s) | 1900.0/1770.0 | 135 | 2.4 | 0.88 | 0.0>0.0 | 1 | 0 | pedal rose at steady input speed (possible lock-up schedule release; compare relock pedal V) |
| 18:10:34 | partial slip | 1.48 (1.64) | 80.7 (age 0.4 s) | 4th (age 2.3 s) | 2000.0/1950.0 | 126 | 1.5 | 0.88 | 100.0>31.8 | 1 | 0 | pedal lifted / idle flag set (coast or lift-off release) |
| 18:10:39 | partial slip | 1.48 (1.0) | 73.5 (age 2.7 s) | 4th (age 7.7 s) | 1850.0/1740.0 | 173 | 3.7 | 0.88 | 100.0>31.8 | 1 | 0 | pedal rose at steady input speed (possible lock-up schedule release; compare relock pedal V) |
| 18:11:59 | full release | 1.31 (1.06) | 46.7 (age 1.4 s) | 4th (age 0.4 s) | 1391.0/1140.0 | >=204 | 3.5 | 0.92 | 0.0>0.0 | 0 | 0 | pedal rose at steady input speed (possible lock-up schedule release; compare relock pedal V) |
| 18:12:04 | full release | 1.33 (1.3) | 48.8 (age 3.6 s) | 4th (age 5.4 s) | 1350.0/1140.0 | >=204 | 6.7 | 0.9 | 0.0>0.0 | 0 | 0 | no clear cause in the logged channels |
| 18:12:13 | full release | 1.31 (1.24) | 49.2 (age 3.9 s) | 4th (age 5.8 s) | 1300.0/1110.0 | >=204 | 2.3 | 0.88 | 0.0>0.0 | 0 | 0 | pedal rose at steady input speed (possible lock-up schedule release; compare relock pedal V) |
| 18:12:19 | full release | 1.29 (1.06) | 46.6 (age 0.4 s) | 4th (age 2.3 s) | 1300.0/1140.0 | >=204 | 1.8 | 0.88 | 0.0>0.0 | 1 | 0 | pedal rose at steady input speed (possible lock-up schedule release; compare relock pedal V) |

## Trends

- atf_C: 62.0 -> 66.0 (min 62, max 67, 4.0 per 10 min)

## Data quality

- 26 slow channels (ac_relay, atf_C, brake, dcc_duty_pct, elc_relay_V, fault_96 and 20 more) were refreshed only every ~8.67 s; between refreshes the CSV repeats the last value. Speed, gear, DCC duty and flag values at an event can be that stale (see *_age_s).
- Fast channels (dcc_slip_rpm, engine_rpm, input_rpm, pedal_V, theo_pressure) were refreshed every cycle, about 5.3 Hz.
- DCC slip saturates at raw 0 and 255 (204 rpm shown): treat those samples as 'at least', not exact.
- 5.26 rows/s, median row gap 0.188 s, largest 0.4 s.
