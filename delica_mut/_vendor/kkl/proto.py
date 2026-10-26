"""Slow-init helper from mitsu-kkl proto.py (MIT, see LICENSE in this folder).

Trimmed for delica-4m40-diag: the other probe strategies and the DTC-clear helper were removed
because this project is read-only. Only the 5-baud wake-up and its capture remain.
"""

from .link import now  # noqa: F401  (kept for parity with upstream imports)


def _hex(pairs):
    return " ".join(f"{b:02X}" for _, b in pairs) or "-"


def _ms(dt):
    return round(dt * 1000, 1)


def _slow_init(kl, addr, baud, method, lline, bit_ms, idle_ms, sync_timeout, keep_open):
    """5-baud init + capture of the ECU's answer. With keep_open the capture stops
    right after KB2 so the caller can still answer ~KB2 inside W4."""
    kl.set_baud(baud)
    kl.discard()
    kl.reset_line_stats()
    i0 = len(kl.buf)
    init = kl.five_baud(addr, bit_ms / 1000, idle_ms / 1000, method, lline)
    i1 = len(kl.buf)
    kl.reset_line_stats()  # our own break sets BI; count only what arrives after the init

    def have_kb():
        bs = [b for _, b in kl.buf[i1:]]
        return 0x55 in bs and len(bs) - bs.index(0x55) >= 3

    kl.wait_for(have_kb, sync_timeout)
    if not (keep_open and have_kb()):
        kl.sleep(0.1)  # let trailing bytes arrive
    post = kl.buf[i1:]
    kl.pos = len(kl.buf)

    res = {"loopback": len(kl.buf[i0:i1]) if method != "bitbang" else "".join(map(str, init["readback"])),
           "edges_ms": init["edges_ms"], "post": _hex(post)}
    sync = None
    bs = [b for _, b in post]
    if 0x55 in bs:
        k = bs.index(0x55)
        sync = {"pre": _hex(post[:k]), "w1_ms": _ms(post[k][0] - init["t_stop_end"])}
        if len(bs) >= k + 3:
            sync.update(kb=f"{bs[k + 1]:02X} {bs[k + 2]:02X}", kb1=bs[k + 1], kb2=bs[k + 2],
                        t_kb2=post[k + 2][0])
    return res, post, sync


def _base_outcome(res, post, sync, kl):
    res["line"] = dict(kl.ls_counts)
    if sync:
        res["sync"] = {k: v for k, v in sync.items() if k not in ("kb1", "kb2", "t_kb2")}
        return "HANDSHAKE" if "kb" in sync else "SYNC"
    return "NOISE" if post or kl.ls_counts else "SILENT"
