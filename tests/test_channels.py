import json

import pytest

from delica_mut import ENGINE, GEARBOX
from delica_mut.channels import BY_ECU, Decoder, columns, load_tables, steinhart_hart


def gb(**raw):
    return Decoder(GEARBOX).decode({int(k[1:], 16): v for k, v in raw.items()})


def en(raw, **kw):
    return Decoder(ENGINE, **kw).decode({(int(k[1:], 16) if isinstance(k, str) else k): v for k, v in raw.items()})


def test_gearbox_linear_formulas():
    d = gb(r10=43, r11=69, r12=100, r13=102, r14=45, r15=70, r2A=93, r44=31, r1A=252)
    assert d["engine_rpm"] == 2150
    assert d["input_rpm"] == 2070 and d["output_rpm"] == 3000
    assert d["atf_C"] == 62
    assert d["pedal_V"] == pytest.approx(0.879, abs=1e-3)
    assert d["theo_pressure"] == pytest.approx(70 * 9.18 - 588, abs=0.1)
    assert d["elc_relay_V"] == pytest.approx(12.09, abs=0.01)
    assert d["speed_kmh"] == pytest.approx(86.8)
    assert d["dcc_duty_pct"] == pytest.approx(98.8, abs=0.05)


def test_solenoid_duty_is_inverted():
    assert gb(r1B=255)["sol_2nd_pct"] == 0.0
    assert gb(r1D=0)["sol_LR_pct"] == 100.0
    assert gb(r1E=128)["sol_OD_pct"] == pytest.approx(100 - 128 / 2.55, abs=0.05)
    assert gb(r1F=255)["sol_UD_pct"] == 0.0


def test_slip_offset_and_saturation():
    assert gb(r18=51)["dcc_slip_rpm"] == 0
    assert gb(r18=60)["dcc_slip_rpm"] == 9
    hi, lo = gb(r18=255), gb(r18=0)
    assert (hi["dcc_slip_rpm"], hi["dcc_slip_sat"]) == (204, "hi")
    assert (lo["dcc_slip_rpm"], lo["dcc_slip_sat"]) == (-51, "lo")
    assert gb(r18=100)["dcc_slip_sat"] == ""


def test_lookups_return_raw_when_unknown():
    assert [gb(r16=v)["shift_pos"] for v in (0, 25, 50, 101, 152, 203)] == ["R", "N/P", "1st", "2nd", "3rd", "4th"]
    assert gb(r16=7)["shift_pos"] == 7
    assert [gb(r27=v)["inhibitor"] for v in (1, 2, 16)] == ["P", "R", "D"]
    assert gb(r27=4)["inhibitor"] == 4


def test_flag_byte_28_bits():
    # 0x94 = key-on idle: pedal released (bit 20 clear = idle ON), A/C relay off (bit 80 set), no brake
    d = gb(r28=0x94)
    assert (d["brake"], d["idle_pos"], d["ac_relay"], d["od_off_sig"], d["hold_sw"], d["tf_low"]) == (0, 1, 0, 0, 0, 0)
    d = gb(r28=0x94 | 0x01)
    assert d["brake"] == 1
    d = gb(r28=0xB4)                     # pedal pressed: bit 20 set -> idle OFF
    assert d["idle_pos"] == 0
    d = gb(r28=0x14)                     # bit 80 clear -> A/C relay ON
    assert d["ac_relay"] == 1
    d = gb(r28=0x94 | 0x40 | 0x02 | 0x08)
    assert (d["od_off_sig"], d["hold_sw"], d["tf_low"]) == (1, 1, 1)
    assert gb(r2B=0x04)["od_off_sw"] == 1 and gb(r2B=0)["od_off_sw"] == 0


def test_fault_slots_are_raw_hex_bytes():
    d = gb(r96=0, r97=0xFF, r98=0x2A)
    assert (d["fault_96"], d["fault_97"], d["fault_98"]) == ("00", "FF", "2A")


def test_missing_inputs_stay_none():
    d = gb(r10=20)
    assert d["engine_rpm"] == 1000 and d["pedal_V"] is None and d["brake"] is None


def test_engine_linear_formulas():
    d = en(dict(r17=34, r16=34, r13=75, r12=203, r18=45, r19=64, r1A=174, r15=0, r1C=230, r1D=0, r1E=128,
                r20=23, r26=25, r21=60, r22=64, r24=64, r25=0))
    assert d["rpm"] == 850 and d["rpm_backup"] == 850
    assert d["boost_kPa"] == pytest.approx(99.75, abs=0.06)
    assert d["baro_kPa"] == pytest.approx(100.3, abs=0.06)
    assert d["boost_gauge_kPa"] == pytest.approx(-0.5, abs=0.15)
    assert d["pedal_V"] == pytest.approx(0.88, abs=0.01)
    assert d["pedal_pct"] == 25.0
    assert d["battery_V"] == pytest.approx(12.76, abs=0.01)
    assert d["tcv_duty_pct"] == 92.0 and d["inj_adjust_V"] == 2.5
    assert d["sleeve_target_pct"] == pytest.approx(9.0, abs=0.1) and d["sleeve_actual_pct"] == pytest.approx(9.8, abs=0.1)
    assert d["timing_actual_CA"] == 12.0 and d["timing_target_CA"] == 12.8
    assert d["ge_duty_pct"] == 25.0 and d["egr_duty_pct"] == 0.0


def test_engine_switch_and_fault_bytes():
    d = en({0x00: 0x40 | 0x10, 0x05: 0x14, 0x51: 0x04, 0x50: 0})
    assert (d["idle_sw1"], d["idle_sw2"], d["ac_sw"], d["st_sw"]) == (1, 1, 0, 0)
    assert (d["is_at"], d["is_van"], d["egr_sol2"]) == (1, 1, 0)
    assert (d["fault_50"], d["fault_51"]) == ("00", "04")


@pytest.mark.parametrize("key,raw,expected", [("coolant_C", 102, 42.9), ("boost_air_C", 84, 42.8), ("fuel_C", 88, 37.8)])
def test_provisional_temperature_curve_matches_van_engine_off(key, raw, expected):
    assert steinhart_hart(raw, key) == pytest.approx(expected, abs=0.2)
    assert Decoder(ENGINE).decode({0x11: 102, 0x10: 84, 0x14: 88})[key] == pytest.approx(expected, abs=0.2)


def test_temperature_out_of_range_is_none_but_raw_is_kept():
    for raw in (0, 3, 252, 255):
        assert steinhart_hart(raw, "coolant_C") is None
    assert steinhart_hart(250, "coolant_C") is None          # inside 4..251 but colder than the -20 C fit limit
    d = en({0x11: 3})
    assert d["coolant_C"] is None and d["coolant_raw"] == 3
    assert steinhart_hart(5, "coolant_C") is None            # hotter than the 110 C fit limit


def test_raw_temperature_toggle_and_user_table(tmp_path):
    assert en({0x11: 102}, raw_temps=True)["coolant_C"] is None
    table = [None] * 256
    table[102] = 55.5
    f = tmp_path / "t.json"
    f.write_text(json.dumps({"coolant_C": table}))
    tables = load_tables(str(f))
    d = en({0x11: 102, 0x10: 84}, tables=tables)
    assert d["coolant_C"] == 55.5
    assert d["boost_air_C"] == pytest.approx(42.8, abs=0.2)    # other channels keep the curve
    assert en({0x11: 5}, tables=tables)["coolant_C"] is None   # null entry = no reading


def test_user_table_validation(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"coolant_C": [1, 2, 3]}))
    with pytest.raises(ValueError):
        load_tables(str(f))
    with pytest.raises(FileNotFoundError):
        load_tables(str(tmp_path / "missing.json"))
    assert load_tables() == {} or isinstance(load_tables(), dict)


def test_no_lookup_table_is_shipped():
    """The temperature channels are curve-only: no 256-entry list lives in the package."""
    import delica_mut.channels as ch
    for name, value in vars(ch).items():
        assert not (isinstance(value, (list, tuple)) and len(value) == 256), name
    assert len(ch.SH_COEFFS["coolant_C"]) == 4   # a, b, c, fit error


def test_columns_unique_and_cover_all_channels():
    for ecu in (GEARBOX, ENGINE):
        cols = columns(ecu)
        assert len(cols) == len(set(cols))
        assert set(Decoder(ecu).decode({}).keys()) == set(cols)
        assert len(BY_ECU[ecu]) > 10
