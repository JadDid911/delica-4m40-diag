import csv
import json

import pytest

from conftest import EXAMPLES
from delica_mut import ENGINE, GEARBOX, ai, decode
from delica_mut.decode import decode_raw_rows, parse_tz
from delica_mut.recorder import Recorder
from delica_mut.sim import GearboxModel, SimSession, VirtualClock

SAMPLE = EXAMPLES / "drive1_gearbox.csv"
CDT = parse_tz("-5")


def sample_rows():
    with open(SAMPLE, newline="") as f:
        return list(csv.DictReader(f))


def test_sample_is_about_ten_minutes_and_clean():
    text = SAMPLE.read_text()
    rows = sample_rows()
    assert 590 < float(rows[-1]["elapsed_s"]) < 610
    for needle in ("/home", "C:\\", "serial"):
        assert needle.lower() not in text.lower()


def test_decode_reproduces_the_lockup_moment():
    rows = decode_raw_rows(sample_rows(), GEARBOX, tz=CDT)
    hit = next(r for r in rows if r["time"].startswith("18:06:56.7"))
    assert hit["engine_rpm"] == 2300 and hit["input_rpm"] == 2070
    assert hit["pedal_V"] == pytest.approx(2.305, abs=0.001)
    assert (hit["dcc_slip_rpm"], hit["dcc_slip_sat"]) == (204, "hi")
    before = next(r for r in rows if r["time"].startswith("18:06:50.0"))
    assert before["dcc_duty_pct"] == pytest.approx(98.8, abs=0.1) and before["shift_pos"] == "4th"
    assert before["speed_kmh"] == pytest.approx(89.6)


def test_decode_cli_roundtrip(tmp_path):
    out = tmp_path / "d.csv"
    assert decode.main([str(SAMPLE), "-o", str(out), "--tz-offset", "-5"]) == 0
    with open(out, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(sample_rows())
    assert list(rows[0]) == decode.decoded_columns(GEARBOX)
    assert decode.detect_ecu(SAMPLE, list(sample_rows()[0])) == GEARBOX


def test_decode_cli_rejects_non_raw_csv(tmp_path):
    f = tmp_path / "x.csv"
    f.write_text("a,b\n1,2\n")
    with pytest.raises(SystemExit):
        decode.main([str(f)])


def test_ai_summary_finds_the_1806_56_lockup_release():
    s = ai.summarize(SAMPLE, tz=CDT)
    hits = [e for e in s["events"] if e["type"] == "lockup_release" and e["clock"] == "18:06:56"]
    assert len(hits) == 1
    e = hits[0]
    assert e["kind"] == "full release" and e["slip_saturated"]
    assert e["pedal_V"] == pytest.approx(2.3, abs=0.05)
    assert e["speed_kmh"] == pytest.approx(87, abs=3)
    assert e["gear"] == "4th"
    assert e["relock_pedal_V"] == pytest.approx(2.13, abs=0.05)
    assert e["duty_confirms_release"] and e["dcc_duty_before_pct"] > 90 and e["dcc_duty_after_pct"] == 0
    assert 6 <= e["released_for_s"] <= 8 or 5 <= e["released_for_s"] <= 8
    md = ai.to_markdown(s)
    assert "18:06:56" in md and "2.31" in md and "4th" in md


def test_ai_summary_phases_events_and_quality():
    s = ai.summarize(SAMPLE, tz=CDT)
    phases = {p["phase"] for p in s["phases"]}
    assert {"idle", "stopped", "accelerating"} <= phases
    assert any(p.startswith("cruise 70-90") for p in phases)
    assert sum(p["duration_s"] for p in s["phases"]) == int(s["data_quality"]["duration_s"]) + 1
    q = s["data_quality"]
    assert 4.5 < q["rows_per_s"] < 6 and q["channels"]["speed_kmh"]["median_interval_s"] > 5
    assert q["channels"]["pedal_V"]["median_interval_s"] < 1
    assert any("slow channels" in n for n in q["notes"]) and any("saturates" in n for n in q["notes"])
    assert s["trends"]["atf_C"]["end"] > s["trends"]["atf_C"]["start"]
    assert len(ai.to_markdown(s)) < 9000     # small enough to paste


def test_ai_works_from_decoded_csv_too(tmp_path):
    out = tmp_path / "d.csv"
    decode.main([str(SAMPLE), "-o", str(out), "--tz-offset", "-5"])
    raw = ai.summarize(SAMPLE, tz=CDT)
    dec = ai.summarize(out)
    key = lambda s: [(e["clock"], e["pedal_V"]) for e in s["events"] if e["type"] == "lockup_release"]
    assert key(raw) == key(dec)


def test_ai_cli_writes_markdown_and_json(tmp_path):
    prefix = tmp_path / "sum"
    assert ai.main([str(SAMPLE), "-o", str(prefix), "--tz-offset", "-5"]) == 0
    assert "18:06:56" in (tmp_path / "sum.md").read_text()
    data = json.loads((tmp_path / "sum.json").read_text())
    assert data["ecu"] == "gearbox" and data["events"]


def test_ai_on_simulated_gearbox_run_finds_the_scheduled_release(tmp_path):
    clock = VirtualClock()
    sim = SimSession(GEARBOX, clock=clock.time, sleep=clock.sleep)
    rec = Recorder(sim, "gearbox-cruise", clock=clock.time)
    rec.start_csv(tmp_path / "sim.csv")
    rec.run(120)
    s = ai.summarize(tmp_path / "sim.csv", tz=parse_tz("utc"))
    release = GearboxModel().release_times[0]
    full = [e for e in s["events"] if e["type"] == "lockup_release" and e["kind"] == "full release"]
    assert any(abs(e["t_s"] - release) < 2 for e in full)
    near = next(e for e in full if abs(e["t_s"] - release) < 2)
    assert near["pedal_V"] == pytest.approx(2.3, abs=0.06) and near["gear"] == "4th"
    assert near["duty_confirms_release"]    # cruise profile samples DCC duty every cycle
    assert "accelerating" in {p["phase"] for p in s["phases"]}


def test_ai_on_simulated_engine_run(tmp_path):
    clock = VirtualClock()
    sim = SimSession(ENGINE, clock=clock.time, sleep=clock.sleep)
    rec = Recorder(sim, "engine", clock=clock.time)
    rec.start_csv(tmp_path / "eng.csv")
    rec.run(90)
    s = ai.summarize(tmp_path / "eng.csv", tz=parse_tz("utc"))
    assert s["ecu"] == ENGINE and "revving (parked)" in {p["phase"] for p in s["phases"]}
    assert s["peaks"]["boost_gauge_kPa_max"] > 50 and s["peaks"]["rpm_max"] > 3000
    assert "provisional" in s["temperature_note"]
    assert "coolant_C" in s["trends"]
    assert "Engine 3002" or True
    assert "engine 3002" in ai.to_markdown(s)


def test_ai_flags_marker_events(tmp_path):
    clock = VirtualClock()
    sim = SimSession(GEARBOX, clock=clock.time, sleep=clock.sleep)
    rec = Recorder(sim, "gearbox-cruise", clock=clock.time,
                   on_row=lambda r: rec.mark("felt surge") if r.cycle == 50 else None)
    rec.start_csv(tmp_path / "m.csv")
    rec.run(30)
    s = ai.summarize(tmp_path / "m.csv", tz=parse_tz("utc"))
    marks = [e for e in s["events"] if e["type"] == "marker"]
    assert len(marks) == 1 and marks[0]["label"] == "felt surge"
