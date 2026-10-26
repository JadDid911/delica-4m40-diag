"""Per-ECU request allowlists. Every byte that goes on the K-line passes through Guard.check().

Gearbox (F3 06): reads 00-BF plus the FE/FF ID reads. 0xC0-0xFD are never sent.
Engine (3002):   ONLY the documented read list below, FE/FF, and the one-shot ROM-ID reads 80/81/82.
                 This ECU has service commands inside 00-BF (B1/B2/BA/BB/BE/BF), so "read everything
                 below C0" is NOT safe here.
Nothing in this project writes, clears codes (FC / CA), runs actuator tests or flashes.
"""

from . import ECUS, ENGINE, GEARBOX

ID_READS = frozenset({0xFE, 0xFF})

GEARBOX_READS = frozenset(range(0x00, 0xC0))

ENGINE_READS = frozenset(
    list(range(0x00, 0x07))        # switch bytes
    + list(range(0x10, 0x1B))      # temperatures, pressures, rpm, pedal, battery
    + [0x1C, 0x1D, 0x1E]           # TCV duty, target EGR, injection adjust
    + [0x20, 0x21, 0x22]           # control sleeve target, injection timing actual/target
    + [0x24, 0x25, 0x26]           # GE duty, EGR duty, control sleeve actual
    + [0x50, 0x51, 0x52, 0x53]     # fault bit bytes (read only; clearing is FC and is never sent)
)
ENGINE_ROM_ID_READS = (0x80, 0x81, 0x82)  # each allowed once per session

# Documented service / actuator commands on the engine ECU. Listed so tests can prove we never send them.
ENGINE_FORBIDDEN_EXAMPLES = frozenset({0xB1, 0xB2, 0xBA, 0xBB, 0xBE, 0xBF, 0xFC}
                                      | set(range(0xC0, 0xFD)))


class SafetyError(RuntimeError):
    """Raised before any byte is sent; the request is not transmitted."""


def allowed_reads(ecu):
    if ecu == GEARBOX:
        return GEARBOX_READS | ID_READS
    if ecu == ENGINE:
        return ENGINE_READS | ID_READS | frozenset(ENGINE_ROM_ID_READS)
    raise SafetyError(f"unknown ECU {ecu!r}; expected one of {ECUS}")


def data_reads(ecu):
    """Requests that may be polled repeatedly (no ID or ROM reads)."""
    return GEARBOX_READS if ecu == GEARBOX else ENGINE_READS


class Guard:
    """Stateful allowlist for one session (tracks the one-shot ROM-ID reads)."""

    def __init__(self, ecu):
        allowed_reads(ecu)  # validates ecu
        self.ecu = ecu
        self._rom_done = set()

    def check(self, cmd):
        if not isinstance(cmd, int) or not 0 <= cmd <= 0xFF:
            raise SafetyError(f"request {cmd!r} is not a byte")
        if cmd in data_reads(self.ecu) or cmd in ID_READS:
            return cmd
        if self.ecu == ENGINE and cmd in ENGINE_ROM_ID_READS:
            if cmd in self._rom_done:
                raise SafetyError(f"engine ROM-ID read {cmd:02X} is one-shot and was already done")
            self._rom_done.add(cmd)
            return cmd
        raise SafetyError(f"{self.ecu} request 0x{cmd:02X} is not on the read allowlist; not sent")


def check_profile_ids(ecu, ids):
    """Reject a profile that lists a request the ECU may not receive."""
    bad = [i for i in ids if i not in data_reads(ecu)]
    if bad:
        raise SafetyError(f"{ecu} profile contains non-allowlisted requests: "
                          + " ".join(f"{i:02X}" for i in bad))
    return list(ids)
