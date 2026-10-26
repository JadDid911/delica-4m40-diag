# Case study: a "surge" at 87 km/h that was the lock-up schedule

This is a real example from the first drive of the test van (1999 Delica Space Gear 4M40 EFI, automatic). It shows what
the tools produce and how to read them. The data is in `examples/drive1_gearbox.csv`; the summary the AI tool makes from it
is `examples/drive1_gearbox.ai-summary.md`.

## The complaint

"At light cruise in top gear it hesitates, as if the engine misses, then it carries on."

The gearbox computer (F3 06) was logged for about 14 minutes (10 minutes are in the sample). No engine computer data was
available yet.

## What the log shows (18:06:50 to 18:07:04)

Gear: 4th, speed about 87 km/h, throughout.

| Time | Engine rpm | Input shaft rpm | Lock-up slip | Lock-up duty | Pedal | ATF |
| --- | --- | --- | --- | --- | --- | --- |
| 18:06:50 | 2,150 | 2,130 | about 0 | 99 % (locked) | 2.17 V | 66 C |
| 18:06:55 | 2,100 | 2,070 | about 0 | locked | 2.27 V | 66 C |
| **18:06:56** | **2,250 to 2,300** | 2,070 | **204 or more (saturated)** | **0 % (released)** | **2.31 V** | 67 C |
| 18:07:00 | 2,250 | 2,070 | 204 or more | 0 % | 2.05 V | 67 C |
| 18:07:02 | 2,100 | 2,040 | 55 falling to 6 | re-locking | 2.13 V | 67 C |

In plain English:

1. The pedal crept up from 2.17 V to 2.31 V over about six seconds while speed stayed the same.
2. At about **2.3 V** the gearbox computer **released the torque-converter lock-up**. The engine jumped about 150 to 200 rpm
   (the converter started to slip) while the car speed did not change. That jump in revs with no speed change is the "miss" you feel.
3. About six seconds later, when the pedal came back to about 2.1 V, the lock-up engaged again.

The AI summary surfaces the same event as one table row: pedal 2.31 V (2.22 V five seconds before), about 87 km/h, 4th, engine
2,300 rpm and input 2,070 rpm, slip 204 or more, released for about 6 s, re-locked at 2.13 V, lock-up duty 98.8 to 0 %, and the
cause hint "pedal rose at steady input speed".

## How it repeats

Across the 4th-gear transitions at highway speed that were sampled quickly in the whole drive, the lock-up released at
about 2.30 V of pedal and re-locked at 1.80, 2.11 and 1.64 V. In the sample window the same pattern shows up again at lighter pedal as
*partial slip*: duty 31 to 38 % and slip 78 to 153 rpm at 1.6 to 1.8 V. The summary lists these as "partial slip" so they are
not confused with full releases.

## Interpretation

This looks like the gearbox computer's normal **lock-up schedule with hysteresis**: it unlocks at a higher pedal voltage than
the one at which it locks again, so the lock-up does not flutter. At 87 km/h the pedal that holds speed on this van (about 2.2 V,
roughly 40 % of pedal travel) sits right under the unlock line. A small change in foot pressure, a gust of wind or a slight
gradient is enough to cross it, and the lock-up cycles off and on.

Two checks that were done:

- **Idle position** (flag in request 28) and **brake** were correct in every fresh sample (24 of 24 on the throttle,
  40 of 40 with the foot off). Neither switch caused the release.
- The DCC duty drop to 0 % lines up with the slip jump, so the computer *commanded* the release; it was not a slipping clutch
  that nobody asked for.

## What is still open

- The sample also contains full releases at about 46 to 49 km/h in 4th with the pedal near 1.3 V (18:11:59 to 18:12:19). The
  summary lists them; this case study does not explain them (they may be shifts or a lower-speed lock-up schedule).
- **Is about 2.2 V of pedal at 87 km/h normal for this van?** If the engine is down on power (boost leak, timing, fuel, air
  filter) or the van carries extra load (tyres, roof load, dragging brakes), the cruise pedal moves closer to the unlock line and
  the surge gets more frequent. That needs engine computer data (boost, timing, sleeve) or a back-to-back load check.
- The pedal voltages and speeds are the computer's own readings and were not checked with a meter or GPS.
- In this sample, speed, gear and lock-up duty were refreshed only every 8 to 9 seconds (the `gearbox-cruise` profile in this
  release reads them every cycle). Event values for those channels can be several seconds old; the summary prints their age.

## Next logs to take

1. Log the **gearbox-cruise** profile on the same road, same speed, and press **Mark event** when you feel the surge.
2. Log the **engine** profile (separate outing, or after a re-connect) to look at boost, timing target versus actual and
   control sleeve target versus actual at the same cruise.
3. Compare the cruise pedal voltage for the same speed with and without extra load.
