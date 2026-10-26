import pytest

from delica_mut import ENGINE, GEARBOX, sessions
from delica_mut.safety import SafetyError
from delica_mut.sessions import KLineSession, SessionLost, WakeError


class FakeKL:
    """Echoes every byte and answers requests from a table; records everything transmitted."""

    def __init__(self, answers):
        self.answers, self.sent = answers, []

    def send(self, data):
        self.sent.extend(data)
        self.last = data[0]
        return True, 0.0

    def read_until_idle(self, idle, timeout, first_timeout=None):
        v = self.answers.get(self.last)
        return [] if v is None else ([(0.0, v)] if isinstance(v, int) else [(0.0, b) for b in v])

    def sleep(self, s):
        pass

    def trim(self):
        pass


@pytest.fixture
def slow_init(monkeypatch):
    calls = []

    def fake(sync):
        def _slow_init(kl, addr, baud, method, lline, bit_ms, idle_ms, sync_timeout, keep_open):
            calls.append(dict(addr=addr, baud=baud, method=method, bit_ms=bit_ms, idle_ms=idle_ms))
            kb = {"kb1": sync[0], "kb2": sync[1]} if sync else None
            return {"post": "55 %02X %02X" % sync if sync else "-"}, [], kb
        monkeypatch.setattr(sessions.proto, "_slow_init", _slow_init)
        return calls
    return fake


def test_gearbox_wake_recipe(slow_init):
    calls = slow_init((0x70, 0x85))
    kl = FakeKL({0xFE: 0xF3, 0xFF: 0x06})
    s = sessions.wake(kl, GEARBOX)
    assert calls == [dict(addr=0x01, baud=15625, method="break", bit_ms=200, idle_ms=1500)]
    assert kl.sent == [0xFE, 0xFF] and s.ecu_id == "F3 06"


def test_engine_wake_recipe(slow_init):
    calls = slow_init((0xEF, 0x85))
    kl = FakeKL({0xFE: 0x30, 0xFF: 0x02})
    s = sessions.wake(kl, ENGINE)
    assert calls == [dict(addr=0x00, baud=15625, method="break", bit_ms=200, idle_ms=10000)]
    assert kl.sent == [0xFE, 0xFF] and s.ecu_id == "30 02"


def test_wrong_keywords_send_nothing(slow_init):
    slow_init((0xEF, 0x85))     # engine keywords answered to the gearbox address
    kl = FakeKL({0xFE: 0xF3, 0xFF: 0x06})
    with pytest.raises(WakeError):
        sessions.wake(kl, GEARBOX)
    assert kl.sent == []


def test_no_handshake_sends_nothing(slow_init):
    slow_init(None)
    kl = FakeKL({})
    with pytest.raises(WakeError):
        sessions.wake(kl, ENGINE)
    assert kl.sent == []


def test_unexpected_id_stops_after_id_reads(slow_init):
    slow_init((0xEF, 0x85))
    kl = FakeKL({0xFE: 0x30, 0xFF: 0x03})     # a 3003 engine: not the validated profile
    with pytest.raises(WakeError):
        sessions.wake(kl, ENGINE)
    assert kl.sent == [0xFE, 0xFF]


def test_dropped_reply_raises_session_lost_and_blocked_bytes_never_sent():
    kl = FakeKL({0x17: 34})
    s = KLineSession(kl, ENGINE)
    assert s.query(0x17) == 34
    with pytest.raises(SessionLost):
        s.query(0x18)            # no answer
    with pytest.raises(SafetyError):
        s.query(0xB1)
    assert kl.sent == [0x17, 0x18]


def test_two_byte_reply_is_a_lost_session():
    kl = FakeKL({0x10: [1, 2]})
    with pytest.raises(SessionLost):
        KLineSession(kl, GEARBOX).query(0x10)
