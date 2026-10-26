# AI analysis

A 10-minute log is a few thousand rows and hundreds of kilobytes of numbers. Pasting that into a chat wastes the
AI's attention and usually gets a vague answer. Instead, give it the **summary**: a few kilobytes that already contain
the drive phases, the events, the trends and the data-quality caveats.

```
delica-ai logs/20261025-180300_gearbox_gearbox-cruise.csv        # writes <name>.ai-summary.md and .json
delica-ai logs/....csv --stdout                                  # just print the Markdown
delica-ai logs/....csv --tz-offset -5                            # clock times in UTC-5 (default: this machine)
```

The input can be the raw CSV from `delica-log` or the decoded CSV from `delica-decode`. For the dashboard there is also an
"AI summary (.md)" button that summarises the recording in progress.

Sizes for the sample drive in `examples/`: raw CSV 380 KB (about 3,157 rows), summary Markdown 6 KB (about 2,000 tokens).

## What the summary contains

- **Drive phases:** engine off, idle, stopped (in gear), accelerating, steady cruise by speed band (0-30, 30-50, 50-70, 70-90,
  90-110, 110+ km/h), coasting (pedal at idle), slowing. Each phase has duration, speed, rpm, pedal, gear, share of time locked
  and ATF temperature (engine logs: boost, timing and sleeve error, coolant, battery).
- **Lock-up events (gearbox):** each time the damper clutch (lock-up) slip jumps from locked to released, with the pedal
  voltage at that moment and 5 s earlier, speed, gear, engine and input rpm, peak slip, how long it stayed released, the pedal
  voltage when it re-locked, the DCC duty before and after, the idle and brake flags, and a cause hint (shift, lift-off,
  acceleration, pedal creeping up at steady speed). Full release and partial slip are told apart.
- **Engine events:** idle rpm dips with the idle switch states, non-zero fault bytes.
- **Your markers:** what the pedal, rpm and speed were when you pressed "Mark event" or typed a label.
- **Trends:** ATF (or coolant, boost air, fuel, battery) start, end, min, max and change per 10 minutes.
- **Data quality:** rows per second, which channels were refreshed every cycle and which only every few seconds,
  saturated slip, logging stalls.

## How to give it to the AI

1. Run `delica-ai` on the log. Open the `.ai-summary.md`.
2. Paste the whole Markdown into the chat after one of the prompts below. Keep the prompt and summary together in one message.
3. If the AI asks for more, paste a short slice of the decoded CSV (30 to 60 rows around the time it names), not the whole file.
4. Attach `docs/CHANNELS.md` only if you want it to judge the confidence of a channel; the summary already states the key caveats.
5. Treat the answer as a hypothesis. The summary shows what the computers *reported*; it cannot see a boost leak or a worn
   clutch. Ask it what to measure next.

Privacy: the summary contains clock times and driving data, no serial numbers, no file paths and no GPS. Check it before you
post it publicly.

## Prompt templates

Replace the text in angle brackets. Put the summary where it says SUMMARY.

### 1. Diagnose my lock-up surge

```
I have a 1999 Mitsubishi Delica Space Gear (4M40 turbo diesel, 4-speed electronic automatic, JDM). At steady cruise in
4th gear around <speed> km/h I feel a surge or hesitation. Below is a log summary from the gearbox computer made with
delica-4m40-diag. "DCC slip" is the torque-converter lock-up clutch slip; a jump from about 0 to 204+ rpm means the
lock-up released. "pedal V" is the accelerator position sensor.

Please:
1. Say whether the lock-up releases line up with my surge (use the clock times in the table).
2. Say what pedal voltage the releases happened at and what it re-locked at, and whether that looks like a lock-up
   schedule with hysteresis rather than a fault.
3. Note which values in the table are stale (see Data quality) and which conclusions they weaken.
4. Tell me what other checks would separate "normal schedule, my cruise pedal sits on the unlock line" from "engine is down
   on power" or "lock-up solenoid or clutch problem".
Do not invent numbers that are not in the summary. Quote the rows you use.

SUMMARY:
<paste the .ai-summary.md here>
```

### 2. Is my engine healthy (boost, timing, fuel)?

```
This is a summary from the engine computer (ID 3002) of a 1999 Mitsubishi Delica Space Gear 4M40 EFI turbo diesel, made
with delica-4m40-diag. Notes: the temperature channels are provisional (about +/-3 C). Boost is shown as gauge pressure
(absolute minus barometric). Timing and control sleeve are reported as actual and target; the error columns are the mean
absolute difference.

Please review:
- boost versus rpm and pedal in the revving or driving phases (does it build and hold?),
- injection timing actual versus target and control sleeve actual versus target (do they track? is there a lag or offset?),
- idle rpm stability and any idle dips, and what the idle switch states were then,
- battery voltage and coolant/fuel/boost-air temperature behaviour,
- any fault bytes (raw hex; I will look the bits up myself).
Separate what the data shows from what it cannot show (it was logged ~5 times per second; parked revs are not a load test).
Finish with a ranked list of the next measurements, each with how to do it safely.

SUMMARY:
<paste the .ai-summary.md here>
```

### 3. Explain this event

```
In this log summary from my Delica (gearbox or engine, see the title), I want you to explain the event at <clock time>
(row "<paste the row>" or marker "<my label>"). I felt: <what you felt>.

Explain in plain English:
- what the computer reported just before, at and just after that moment,
- the most likely explanations in order, and what in the data supports or contradicts each,
- what you cannot tell because of sampling (check Data quality and the "age" figures),
- one inexpensive thing I can try or log to confirm.
Keep it short and do not go beyond the numbers shown.

SUMMARY:
<paste the .ai-summary.md here>
```

### 4. What should I log next?

```
Here is a summary of my last log from a Delica 4M40 (gearbox F3 06 or engine 3002; see the title). Based on the questions
I still have (<your questions>), tell me exactly what to log next:
- which computer and which profile (gearbox-cruise, gearbox-full, gearbox-flags, engine),
- what to do while logging (speed, gear, pedal movements, A/C on or off, when to press "Mark event" and what to type),
- how long, and in what conditions (cold start, warm, flat road, a hill),
- what result would confirm or rule out each suspect.
Remember: the two computers cannot be logged at the same time, the engine profile reads a fixed list of 31 values, and I can
only log while it is safe. Give me a numbered plan I can follow in one outing.

SUMMARY:
<paste the .ai-summary.md here>
```

## Tips

- Press **Mark event** (or type a label and Enter in `delica-log`) whenever you feel the symptom. Markers show up with the
  pedal, rpm and speed at that moment, which is the most useful thing you can give an AI.
- Log the **gearbox-cruise** profile for surge and lock-up questions: it reads slip, DCC duty, pedal, speed, gear and flags
  every cycle. The `gearbox-full` profile refreshes most values only every few seconds.
- Ask for the result in a table or bullet list and ask it to name the rows it relied on, so you can check them.
