# Contributing

Thank you for helping. The most valuable contributions are **recordings from other vans** and **confirmed channel
meanings**. Read [docs/SAFETY.md](docs/SAFETY.md) first: this project only reads, and contributions must keep it that way.

## Reporting another ECU ID safely

You have a different van (other year, petrol, other transmission) and the wake-up answers with an ID that is not `F3 06` or
`30 02`. Do this and nothing else:

1. Use the stock recipes in [docs/PROTOCOL.md](docs/PROTOCOL.md). The program stops after the ID check when the ID is not the
   validated one. That stop is the intended behaviour and the result is the report: copy the message.
2. **Do not** add the ID to the allowlist yourself and do not sweep. On the engine computer, service commands live inside
   `00-BF`; on an unknown computer you cannot know where they are.
3. Open an issue titled "ECU ID <ID bytes>" with:
   - vehicle (market, year, engine, transmission), which computer (engine or gearbox) and the 5-baud address that answered,
   - the `.events.jsonl` from the attempt (it contains no serial numbers or paths),
   - the keyword bytes (`55 xx xx`) and the two ID bytes,
   - how pin 1 was wired and what the check-engine light did,
   - whether the cable is a genuine FT232R.
4. A maintainer will decide on a read list from published, public information and propose a profile **behind the
   allowlist** with tests. Nobody should be told to "try these requests" on an ECU nobody has verified.

## Reporting a channel finding

Open an issue or pull request with: request address, what you did (pedal held, A/C on, key on engine off, gear selected),
the raw bytes before and after (a few rows of the raw CSV), and what the physical quantity was (a meter reading, a
thermometer, the speedometer). A channel moves from `low` or `unverified` to `medium` or `high` only with this kind of evidence.
Cite the evidence in `delica_mut/channels.py`; `docs/CHANNELS.md` is regenerated from it.

## Rules for code changes

- Read-only. No writes, no code clears, no actuator tests, no flashing, no new request that is not on an allowlist.
- Do not copy third-party databases, lookup tables or fault-description texts into the repo (see
  [third_party/README.md](third_party/README.md)). Publish our own facts with our own evidence.
- No serial numbers, personal names or local paths in code, docs or sample data.
- Add or update tests. `pytest` must pass offline; it uses the built-in simulator, not hardware.
- Avoid em dashes in documentation.

## Development

```
pip install -e ".[dev]"
pytest
delica-live --sim        # demo dashboard
```

Regenerate `docs/CHANNELS.md` tables after editing channels: `python -m delica_mut.channels gearbox` and `engine`, paste
between the BEGIN/END markers (`pytest` checks they match).
