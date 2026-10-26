import csv
import json

import pytest

from delica_mut import ENGINE, GEARBOX
from delica_mut.decode import decode_raw_rows
from delica_mut.recorder import PROFILES, EventLog, Recorder, csv_header
from delica_mut.sessions import WakeError
from delica_mut.sim import GearboxModel, SimSession, VirtualClock


def make(ecu, **kw):
    clock = VirtualClock()
    return clock, SimSession(ecu, clock=clock.time, sleep=clock.sleep, **kw)


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("profile", ["gearbox-cruise", "gearbox-full", "gearbox-flags", "engine"])
def test_records_wide_csv_with_fresh_column(tmp_path, profile):
    p = PROFILES[profile]
    clock, sim = make(p.ecu)
    events = EventLog(tmp_path / "e.jsonl")
    rec = Recorder(sim, profile, clock=clock.time, log=events)
    rec.start_csv(tmp_path / "x.csv")
    result = rec.run(60)
    events.close()
    rows = read_csv(tmp_path / "x.csv")
    assert result["reason"] == "duration reached" and len(rows) == result["cycles"] > 100
    assert list(rows[0]) == csv_header(p)
    ids = {f"{i:02X}" for i in p.ids}
    for r in rows[:50]:
        fresh = r["fresh"].split()
        assert set(fresh) <= ids and set(p.fast) <= {int(x, 16) for x in fresh}
        for x in fresh:
            assert r[f"r{x}"] != ""
    # slow channels are refreshed round-robin: every id appears in a full rotation
    seen = {x for r in rows for x in r["fresh"].split()}
    assert seen == ids
    names = [json.loads(line)["ev"] for line in (tmp_path / "e.jsonl").read_text().splitlines()]
    assert names[0] == "csv_start" or "run_start" in names
    assert "run_end" in names


def test_markers_and_csv_toggle(tmp_path):
    clock, sim = make(GEARBOX)
    events = EventLog(tmp_path / "e.jsonl")
    rec = Recorder(sim, "gearbox-cruise", clock=clock.time, log=events)
    rows_seen = []
    rec.start_csv(tmp_path / "a.csv")

    def on_row(row):
        rows_seen.append(row)
        if row.cycle == 10:
            rec.mark("=SUM(A1) pedal down")
        if row.cycle == 20:
            rec.stop_csv()
            rec.start_csv(tmp_path / "b.csv")

    rec.on_row = on_row
    rec.run(10)
    events.close()
    a, b = read_csv(tmp_path / "a.csv"), read_csv(tmp_path / "b.csv")
    assert len(a) == 20 and len(b) > 20
    assert a[0]["marker"] == "start" and b[-1]["marker"] == "'=SUM(A1) pedal down"   # formula-injection guard
    assert any(json.loads(l)["ev"] == "marker" for l in (tmp_path / "e.jsonl").read_text().splitlines())


def test_dropped_session_stops_without_reconnecting(tmp_path):
    clock, sim = make(GEARBOX, fail_after=50)
    woke = []
    rec = Recorder(sim, "gearbox-cruise", clock=clock.time, wake=lambda: woke.append(1))
    rec.start_csv(tmp_path / "x.csv")
    result = rec.run(60)
    assert result["reason"].startswith("session lost") and woke == []
    assert len(sim.sent) == 50


def test_rewake_only_when_explicitly_allowed(tmp_path):
    clock, sim = make(GEARBOX, fail_after=30)
    log = EventLog(tmp_path / "e.jsonl")
    fresh = []

    def wake():
        s = SimSession(GEARBOX, clock=clock.time, sleep=clock.sleep)
        fresh.append(s)
        return s

    rec = Recorder(sim, "gearbox-cruise", clock=clock.time, log=log, wake=wake, max_rewakes=1)
    result = rec.run(20)
    log.close()
    assert result["reason"] == "duration reached" and len(fresh) == 1 and fresh[0].sent
    evs = [json.loads(l)["ev"] for l in (tmp_path / "e.jsonl").read_text().splitlines()]
    assert evs.count("session_lost") == 1 and "rewake_ok" in evs


def test_rewake_failure_stops(tmp_path):
    clock, sim = make(ENGINE, fail_after=40)

    def wake():
        raise WakeError("no handshake")

    result = Recorder(sim, "engine", clock=clock.time, wake=wake, max_rewakes=3, rom_id=False).run(60)
    assert result["reason"].startswith("re-wake failed")


def test_profile_must_match_session():
    clock, sim = make(GEARBOX)
    with pytest.raises(ValueError):
        Recorder(sim, "engine", clock=clock.time)


def test_engine_rom_id_read_once_and_logged(tmp_path):
    clock, sim = make(ENGINE)
    log = EventLog(tmp_path / "e.jsonl")
    Recorder(sim, "engine", clock=clock.time, log=log).run(5)
    log.close()
    roms = [json.loads(l) for l in (tmp_path / "e.jsonl").read_text().splitlines() if '"rom_id_read"' in l]
    assert len(roms) == 1 and roms[0]["requests"] == "80 81 82"


def test_recorded_csv_decodes_to_engineering_units(tmp_path):
    clock, sim = make(GEARBOX)
    rec = Recorder(sim, "gearbox-cruise", clock=clock.time)
    rec.start_csv(tmp_path / "x.csv")
    rec.run(70)
    rows = decode_raw_rows(read_csv(tmp_path / "x.csv"), GEARBOX)
    last = rows[-1]
    assert 700 <= last["engine_rpm"] <= 3500 and 0 <= last["pedal_V"] <= 3.3
    assert any(r["dcc_slip_sat"] == "hi" for r in rows)     # simulated lock-up release saturates the slip channel


def test_sim_scenario_has_one_schedule_release():
    m = GearboxModel()
    assert len(m.release_times) >= 1
    t = m.release_times[0]
    assert 55 < t < 58 and 2.25 < m.state(t)["pedal_V"] < 2.35
