# Protocol notes

Both computers speak the same MUT-style K-line protocol on DLC pin 7 at **15625 baud, 8N1**. A session is: wake the
computer with a slow 5-baud address, read two ID bytes, then poll one-byte requests.

## Wake-up recipes

| | Gearbox (ID F3 06) | Engine (ID 3002) |
| --- | --- | --- |
| Quiet K-line before the address | 1500 ms | **10 s** |
| 5-baud address | `0x01` | `0x00` |
| Bit time | 200 ms, produced with a UART break | 200 ms, UART break |
| Wire shape of the address | low 200 ms, high 200 ms, low 1400 ms, then stop bit | low 1800 ms, then stop bit |
| Then, at 15625 baud, the computer sends | `55 70 85` | `55 EF 85` |
| Tester acknowledges the keywords? | no | no |
| ID reads | request `FE` then `FF` -> `F3` `06` | `FE` then `FF` -> `30` `02` |
| First request before the ID reads | none | none |

Rules the code follows (`delica_mut/sessions.py`):

1. Open the port at 15625 baud, wait 3 s for the line to settle.
2. Hold K quiet for the idle time, send the address with the break method, release.
3. Listen up to 1.5 s (gearbox) or 2 s (engine) for `0x55` followed by two keyword bytes. If the keywords are not exactly
   the expected pair, stop: no request is sent to an unidentified responder.
4. Wait 20 ms, then send `FE` and `FF`. If the ID is not the expected pair, stop.
5. Only then poll the profile.

Requests are **one byte**. On the half-duplex K-line the cable echoes your own byte, so each reply is the echo
followed by **one** data byte. The reply arrives about 4 to 5 ms after the request, so the reader treats 8 ms of
silence as the end of a reply. A missing echo, or anything other than exactly one reply byte, is a lost session.

Typical speed: about 14 ms per request including Python overhead, so the cruise profile (about 11 reads per cycle)
runs at roughly 5 to 7 cycles per second, and a full 192-request sweep takes about 2.5 s.

## Why address 00 failed for the gearbox

The gearbox computer answers address `0x01` (the transmission record in the reference database says address 01 with
keywords `70 85`, and the van agreed). Address `0x00` is the *engine's* and is the usual MUT address, so it was tried first:
the van stayed silent at both 10400 and 15625 baud. Address `0x01` at 15625 baud with a 1500 ms idle answered `55 70 85`
at the first try, and `FE`/`FF` returned `F3 06`, which turned out to be the gearbox. The wake-up recipe for each computer therefore differs in address,
keywords and quiet time; do not reuse one for the other.

## Why the 10 s quiet matters for the engine

The engine computer did not answer address `0x00` in the early short-idle attempts (1500 ms idle, with a pre-query `FE`
sent before the wake-up). It answered `55 EF 85` when the K-line was left quiet for 10 s first and **no request was sent
before the wake-up**. Eight successful connections later it has been reliable that way. Honest caveat: both
changes were made at once, so the evidence does not say which one mattered. A timing field (`W5 = 9400`) in the
reference database for this ECU family is consistent with a long bus-idle requirement, but that is a hypothesis. The code
keeps both: 10 s quiet and no pre-query. Do not shorten the idle time unless you are testing on purpose.

## Session rules

- One session per run. If a reply is lost the run stops and says so. It does not re-initialise by itself: the diagnostic connection can disturb the engine, and a silent re-wake mid-drive would
  hide a failing link. Re-wake is possible only with an explicit flag
  (`delica-log --rewake N`, `delica-live --rewake N`), is logged as `session_lost` / `rewake_attempt` events and gives up
  after N tries.
- Keep the keep-alive simple: polling is the keep-alive. There is no idle period inside a run.
- The computers share pin 7: unplug or stop one session before waking the other.

## Request map

See [CHANNELS.md](CHANNELS.md) for what each request returns and [SAFETY.md](SAFETY.md) for what is allowed.
