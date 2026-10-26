# Safety

This project only **reads**. The rules below are enforced in code (`delica_mut/safety.py`) and by the tests, not just by
convention.

## What the code will and will not send

| Computer | Allowed | Blocked |
| --- | --- | --- |
| Gearbox (F3 06) | read requests `00` to `BF`, ID reads `FE` / `FF` | `C0` to `FD` (service area: code clear, actuator tests) |
| Engine (3002) | **only** `00-06, 10-1A, 1C-1E, 20-22, 24-26, 50-53` (31 reads), `FE` / `FF`, and the one-shot ROM-ID reads `80` `81` `82` | everything else, including `B1 B2 BA BB BE BF` and `C0` to `FD` |

Why the engine list is so strict: the engine computer keeps service commands **inside** the `00-BF` range
(`B1`, `B2`, `BA`, `BB`, `BE`, `BF`: actuator tests). A generic "read everything below C0" sweep is safe on the
gearbox and **unsafe on the engine**. The engine profile therefore lists the documented reads by name.

How it is enforced:

- `Session.query()` is the only way a request byte reaches the cable. It calls `Guard.check()` first; a blocked byte
  raises `SafetyError` **before anything is transmitted**.
- Every recorder profile is checked against its allowlist when the module is imported, so a typo cannot add a request.
- ROM-ID reads (`80`-`82`) are allowed once per session each, at start-up, and are logged, never polled.
- The vendored transport (mitsu-kkl) was trimmed: its DTC-clear helper and other probe strategies are not in this repo.
- Not implemented anywhere: writes, code clears (`FC` on the engine computer), actuator tests, flashing, reprogramming.
- A test (`tests/test_safety.py`) runs every profile against the simulator and asserts the set of transmitted bytes stays in
  the allowlist and never contains a forbidden byte.

## Sessions never reconnect silently

If a reply is lost, the run stops, writes a `session_lost` event and tells you. It does not re-initialise on its own. You
can opt in with `--rewake N` (up to N attempts, each logged); the default is 0.

## Wiring and physical safety

- **Never connect anything to DLC pin 9.** It is the ETACS pulse line; driving it reportedly damaged ETACS units.
- Pin 1 must be grounded for diagnosis mode. Use a switch so you can undo it; see [HARDWARE.md](HARDWARE.md).
- The two computers share pin 7. Log one at a time.
- Park the van for the wake-up. While driving, let a passenger watch the screen or just record. Do not read a laptop or phone
  while driving.
- The diagnostic connection can change engine behaviour (rough or hunting idle was seen on the test van while
  connected). Unplug the cable and turn off the pin 1 jumper when you are done.
- The test van's findings are not a repair manual. Nothing here replaces the factory service manual or a mechanic.

## Network exposure of the dashboard

`delica-live` listens on `127.0.0.1` only. With `--lan` it listens on your network so a phone can connect; the URL
contains a random key that is needed for every request. Anyone who has the URL can view the data and start or stop
logging (they cannot send anything that is not on the allowlist). Stop the program when you are done and use a network you trust.

## Reporting a safety problem

Open an issue (or contact the maintainers privately if it involves hardware damage) with what you did and the event log.
See [CONTRIBUTING.md](../CONTRIBUTING.md).
