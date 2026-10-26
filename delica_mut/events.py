"""Lock-up (damper clutch) release detection shared by delica-ai and the live dashboard.

Release = DCC slip jumps from locked (<= 40 rpm for at least 1 s) to >= 100 rpm within 1.5 s, while the
input shaft turns (>= 1000 rpm) in 3rd/4th (or unknown) gear. The release ends when slip is back under
50 rpm. The matching DCC duty drop to ~0 % is reported alongside when it was sampled.
"""

import bisect

SLIP_LOCKED = 40
SLIP_RELEASED = 100
SLIP_RELOCKED = 50


def detect_lockup_releases(ts, slip, input_rpm=None, gear=None):
    """Parallel lists (time s, slip rpm, input rpm, gear). Returns [(leave_idx, cross_idx, end_idx|None)]."""
    n, out, i = len(ts), [], 1
    while i < n:
        if slip[i] >= SLIP_RELEASED:
            j = i
            while j > 0 and ts[i] - ts[j - 1] <= 1.5 and slip[j - 1] > SLIP_LOCKED:
                j -= 1
            if j > 0 and slip[j - 1] <= SLIP_LOCKED and ts[i] - ts[j - 1] <= 1.5:
                lo = bisect.bisect_left(ts, ts[j] - 1.0)
                sustained = all(v <= SLIP_LOCKED for v in slip[lo:j])
                moving = (input_rpm[i] if input_rpm else 0) or 0
                in_gear = (gear[j] if gear else None) in (None, "3rd", "4th")
                if sustained and moving >= 1000 and in_gear:
                    end = next((k for k in range(i, n) if slip[k] <= SLIP_RELOCKED), None)
                    out.append((j, i, end))
                    i = end if end is not None else n
        i += 1
    return out
