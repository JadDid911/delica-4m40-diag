import re
from pathlib import Path

import pytest

from delica_mut import ENGINE, GEARBOX
from delica_mut import safety
from delica_mut.recorder import PROFILES, Recorder
from delica_mut.safety import ENGINE_FORBIDDEN_EXAMPLES, ENGINE_READS, Guard, SafetyError
from delica_mut.sim import SimSession, VirtualClock

DOCUMENTED_ENGINE = (list(range(0x00, 0x07)) + list(range(0x10, 0x1B)) + [0x1C, 0x1D, 0x1E, 0x20, 0x21, 0x22,
                     0x24, 0x25, 0x26, 0x50, 0x51, 0x52, 0x53])


def test_gearbox_allows_00_to_bf_and_id_reads_only():
    g = Guard(GEARBOX)
    for cmd in list(range(0x00, 0xC0)) + [0xFE, 0xFF]:
        assert g.check(cmd) == cmd
    for cmd in range(0xC0, 0xFE):          # includes 0xCA/0xFC style service commands
        with pytest.raises(SafetyError):
            g.check(cmd)


def test_engine_allows_exactly_the_documented_read_list():
    assert sorted(ENGINE_READS) == sorted(DOCUMENTED_ENGINE)
    assert len(ENGINE_READS) == 31
    g = Guard(ENGINE)
    for cmd in DOCUMENTED_ENGINE + [0xFE, 0xFF]:
        g.check(cmd)


@pytest.mark.parametrize("cmd", sorted(ENGINE_FORBIDDEN_EXAMPLES | {0x07, 0x08, 0x0F, 0x1B, 0x1F, 0x23, 0x27, 0x30, 0x54, 0x7F, 0xFD}))
def test_engine_blocks_service_and_undocumented_requests(cmd):
    with pytest.raises(SafetyError):
        Guard(ENGINE).check(cmd)


def test_engine_service_commands_inside_00_bf_are_listed_and_blocked():
    for cmd in (0xB1, 0xB2, 0xBA, 0xBB, 0xBE, 0xBF):
        assert cmd in ENGINE_FORBIDDEN_EXAMPLES and cmd not in ENGINE_READS
        with pytest.raises(SafetyError):
            Guard(ENGINE).check(cmd)


def test_engine_rom_id_reads_are_one_shot():
    g = Guard(ENGINE)
    for cmd in (0x80, 0x81, 0x82):
        g.check(cmd)
        with pytest.raises(SafetyError):
            g.check(cmd)
    with pytest.raises(SafetyError):
        Guard(GEARBOX).check(0x80 | 0x40)  # gearbox has no ROM-ID reads outside 00-BF; 0xC0 blocked
    Guard(GEARBOX).check(0x80)             # 0x80 is a normal gearbox read


def test_non_byte_and_unknown_ecu_rejected():
    for bad in (-1, 256, "10", None, 1.5):
        with pytest.raises(SafetyError):
            Guard(GEARBOX).check(bad)
    with pytest.raises(SafetyError):
        Guard("abs")


def test_every_profile_is_inside_its_allowlist():
    for p in PROFILES.values():
        safety.check_profile_ids(p.ecu, p.ids)
    assert sorted(PROFILES["engine"].ids) == sorted(DOCUMENTED_ENGINE)
    assert set(PROFILES["gearbox-full"].ids) == set(range(0xC0))
    with pytest.raises(SafetyError):
        safety.check_profile_ids(ENGINE, [0x17, 0xB1])


def test_blocked_request_never_reaches_the_wire():
    clock = VirtualClock()
    sim = SimSession(ENGINE, clock=clock.time, sleep=clock.sleep)
    with pytest.raises(SafetyError):
        sim.query(0xB1)
    assert sim.sent == []


@pytest.mark.parametrize("ecu,profile", [(ENGINE, "engine"), (GEARBOX, "gearbox-cruise"), (GEARBOX, "gearbox-full"),
                                         (GEARBOX, "gearbox-flags")])
def test_recorder_only_sends_allowlisted_bytes(ecu, profile):
    clock = VirtualClock()
    sim = SimSession(ecu, clock=clock.time, sleep=clock.sleep)
    Recorder(sim, profile, clock=clock.time).run(20)
    allowed = safety.allowed_reads(ecu)
    assert sim.sent and set(sim.sent) <= allowed
    if ecu == ENGINE:
        assert not set(sim.sent) & ENGINE_FORBIDDEN_EXAMPLES
        assert [c for c in sim.sent if c in (0x80, 0x81, 0x82)] == [0x80, 0x81, 0x82]   # once each
    else:
        assert not set(sim.sent) & set(range(0xC0, 0xFE))


def test_only_the_session_module_transmits():
    """Static check: the single TX site is KLineSession._read; nothing else writes to the line."""
    pkg = Path(safety.__file__).parent
    offenders = [path.name for path in pkg.glob("*.py")
                 if path.name != "sessions.py" and re.search(r"\.send\(|dev\.write|\.dev\.|kl\.", path.read_text(encoding="utf-8"))]
    assert not offenders, offenders
    vendored = (pkg / "_vendor" / "kkl" / "proto.py").read_text(encoding="utf-8")
    assert "mut_clear" not in vendored and "CLEAR_CMD" not in vendored
