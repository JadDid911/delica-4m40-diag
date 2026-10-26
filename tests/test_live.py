import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from delica_mut.live import LiveHub, serve


@pytest.fixture
def server(tmp_path):
    hub = LiveHub(tmp_path, sim=True, sim_speed=5.0)
    srv = serve(hub, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield hub, base
    hub.stop()
    time.sleep(0.2)
    srv.shutdown()
    srv.server_close()


def get(base, path, headers=None):
    req = urllib.request.Request(base + path, headers=headers or {})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, r.headers, r.read()


def post(base, path, body, token, ctype="application/json"):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": ctype, "X-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def wait_for(fn, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError("timeout")


def state(base):
    return json.loads(get(base, "/api/state")[2])


def test_page_state_channels_and_no_vehicle_access_on_open(server):
    hub, base = server
    status, headers, body = get(base, "/")
    html = body.decode()
    assert status == 200 and hub.key in html and "__TOKEN__" not in html
    assert "http://" not in html.replace("http://www.w3.org", "") and "https://" not in html   # no CDN
    assert "Content-Security-Policy" in headers
    st = state(base)
    assert st["status"] == "idle" and st["sim"] and st["profiles"]["engine"] == ["engine"]
    ch = json.loads(get(base, "/api/channels?ecu=engine")[2])
    assert ch["channels"]["coolant_C"]["confidence"] == "provisional"
    assert "calibration pending" in ch["temperature_note"] and "MMC-Reader" in ch["temperature_note"]
    assert get(base, "/api/channels?ecu=gearbox")[0] == 200
    with pytest.raises(urllib.error.HTTPError):
        get(base, "/api/channels?ecu=abs")


def test_gearbox_sim_end_to_end(server):
    hub, base = server
    assert post(base, "/api/connect", {"ecu": "gearbox", "profile": "gearbox-cruise"}, hub.key)[0] == 200
    wait_for(lambda: state(base)["seq"] > 30)
    st = state(base)
    assert st["status"] == "live" and st["ecu_id"] == "F3 06" and st["recording"]
    assert st["latest"]["pedal_V"] > 0.5 and "dcc_slip_rpm" in st["latest"]
    hist = json.loads(get(base, "/api/history?since=0")[2])
    assert hist["rows"] and hist["rows"][-1]["seq"] == hist["seq"]
    assert "engine_rpm" in hist["rows"][0] and "t" in hist["rows"][0]
    later = json.loads(get(base, f"/api/history?since={hist['seq'] - 3}")[2])["rows"]
    assert len(later) <= 3 + 20

    assert post(base, "/api/mark", {"label": "surge now"}, hub.key)[0] == 200
    wait_for(lambda: any(r["marker"] == "surge now" for r in json.loads(get(base, "/api/history?since=0")[2])["rows"]))

    raw = get(base, "/api/download.csv")[2].decode()
    assert raw.startswith("utc_ms,elapsed_s,cycle,marker,fresh,r") and "surge now" in raw
    dec = get(base, "/api/download.csv?decoded=1")[2].decode()
    assert dec.startswith("time,utc_ms,elapsed_s,marker,engine_rpm")
    summary = get(base, "/api/summary.md")[2].decode()
    assert "Delica 4M40 log summary: gearbox F3 06" in summary

    # record toggle: off then on writes a new file
    first = state(base)["csv_name"]
    assert post(base, "/api/record", {"on": False}, hub.key)[0] == 200
    wait_for(lambda: not state(base)["recording"])
    time.sleep(1.1)   # file names have 1 s resolution
    assert post(base, "/api/record", {"on": True}, hub.key)[0] == 200
    wait_for(lambda: state(base)["recording"] and state(base)["csv_name"] != first)

    assert post(base, "/api/stop", {}, hub.key)[0] == 200
    wait_for(lambda: state(base)["status"] == "stopped")
    assert post(base, "/api/connect", {"ecu": "engine"}, hub.key)[0] == 200


def test_sim_lockup_release_is_detected_live(server):
    hub, base = server
    post(base, "/api/connect", {"ecu": "gearbox"}, hub.key)
    st = wait_for(lambda: (s := state(base)) and s["lockups"] and s, timeout=20)
    e = st["lockups"][0]
    assert e["gear"] == "4th" and 2.25 < e["pedal_V"] < 2.4 and 80 < e["speed_kmh"] < 92


def test_engine_sim(server):
    hub, base = server
    assert post(base, "/api/connect", {"ecu": "engine"}, hub.key)[0] == 200
    wait_for(lambda: state(base)["seq"] > 20)
    st = state(base)
    assert st["ecu_id"] == "30 02" and st["temperature_source"] == "provisional curve"
    lat = st["latest"]
    assert lat["rpm"] > 500 and "coolant_C" in lat and "coolant_raw" in lat and lat["fault_51"] == "00"


def test_bad_requests_are_rejected(server):
    hub, base = server
    assert post(base, "/api/connect", {"ecu": "gearbox"}, "wrong-token")[0] == 403
    assert post(base, "/api/connect", {"ecu": "gearbox"}, hub.key, ctype="text/plain")[0] == 415
    assert post(base, "/api/connect", {"ecu": "abs"}, hub.key)[0] == 400
    assert post(base, "/api/connect", {"ecu": "gearbox", "profile": "engine"}, hub.key)[0] == 400
    assert post(base, "/api/mark", {"label": "x"}, hub.key)[0] == 400          # not connected
    assert state(base)["status"] == "idle"
    with pytest.raises(urllib.error.HTTPError) as err:
        get(base, "/api/state", {"Host": "evil.example"})
    assert err.value.code == 403


def test_downloads_404_before_recording(server):
    hub, base = server
    with pytest.raises(urllib.error.HTTPError) as err:
        get(base, "/api/download.csv")
    assert err.value.code == 404


def test_lan_mode_requires_the_key(tmp_path):
    hub = LiveHub(tmp_path, sim=True)
    srv = serve(hub, "127.0.0.1", 0, lan=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        for path in ("/", "/api/state"):
            with pytest.raises(urllib.error.HTTPError) as err:
                get(base, path)
            assert err.value.code == 403
        assert get(base, f"/?key={hub.key}")[0] == 200
        assert get(base, f"/api/state?key={hub.key}")[0] == 200
    finally:
        srv.shutdown()
        srv.server_close()
