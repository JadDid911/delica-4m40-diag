# Hardware

You need a cable, a way to ground DLC pin 1, and (optionally) a breakout box. Total cost is about $15 to $30.

## The cable: FTDI FT232R "VAG KKL 409.1"

Buy a USB K-line cable sold as **VAG KKL 409.1** (or "KKL USB OBD2") whose chip is an **FTDI FT232R** (the chip
is marked FT232RL; Windows shows "USB Serial Converter", USB ID 0403:6001). It is a USB serial port plus a K-line
transceiver, powered from DLC pin 16.

Why FT232R:

- It can generate the 15625 baud this ECU family uses (a non-standard rate) and send a long UART break, which this
  project uses to produce the slow 5-baud wake-up address.
- The vendored transport (mitsu-kkl) drives it directly through FTDI's D2XX driver on Windows, or as a normal serial port.

Avoid:

| Cable | Problem |
| --- | --- |
| CH340 / CP2102 / PL2303 "KKL" clones | custom baud rates and break timing are unreliable; many do not reach 15625 baud cleanly |
| ELM327 (Bluetooth or USB) | speaks OBD-II protocols only; it cannot do this K-line request/reply protocol |
| HEX-CAN, CAN-only adapters | CAN bus only; these vans have no CAN |
| Anything that "also does pin 9" | see the pin 9 warning below |

Counterfeit FTDI chips exist. Buy from a seller with returns, and keep the official FTDI driver installed.

## Connector and pins (16-pin DLC)

| DLC pin | Use here |
| --- | --- |
| 7 | K-line to the cable (both the gearbox and the engine computer answer here) |
| 16 | +12 V, powers the cable |
| 4 and 5 | ground |
| 1 | must be **grounded** to put the computers in diagnosis mode (the check-engine light then blinks) |
| 9 | **never connect anything** |

Both computers share pin 7, so the program talks to **one at a time**: choose gearbox or engine when you start.

### Pin 9 warning

DLC pin 9 is the ETACS (body computer) pulse line on these vans. Driving it has reportedly damaged ETACS units. This
project never uses pin 9. If you build a breakout box, leave pin 9 out entirely. Do not use a cable or adapter that
connects it.

### Getting pin 1 to ground

Diagnosis mode needs pin 1 tied to ground (pin 4 or 5) with the ignition on. Options, simplest first:

1. A breakout box with a toggle switch between pin 1 and pin 4 (recommended: you can leave diagnosis mode when you
   are done, and the switch is easy to see).
2. A short jumper wire in a DLC test plug between pins 1 and 4 (a 16-pin test plug or a spare male connector).
3. A push-button on the same two pins, held while you turn the key (only if a switch is not an option).

With ignition on and the jumper in, the check-engine light should start blinking. If it does not, the computers are not in
diagnosis mode and the engine computer will probably stay silent. The diagnostic connection itself can change engine
idle on some vans (rough or hunting idle was seen on the test van while connected), so log while parked, and do not
treat idle behaviour while connected as a baseline.

Some owner reports add a 1 kOhm resistor between pin 7 and pin 16 for other tools. The test van worked with the cable as sold
and no resistor; try that first.

## Breakout box

A box with the 16-pin plug, a screw terminal or sockets for pins 4, 7, 16, and a switch for pin 1 to ground is enough. Wire
only the pins in the table. Label the box "no pin 9".

## Software side of the cable

Windows:

1. Plug the cable in; Windows Update usually installs the FTDI driver. If not, install FTDI's "VCP/D2XX" driver (CDM).
2. The default (`auto`) uses the D2XX driver when `ftd2xx.dll` is present, otherwise the COM port.
3. If you use the COM port, set the latency timer to **1 ms** (Device Manager, the COM port, Properties, Port Settings,
   Advanced). The default 16 ms makes every request slow.
4. Use `--port COM5` for a specific port, or `--ftdi-serial` to pick a cable by its FTDI serial number.

Linux:

1. The `ftdi_sio` kernel driver provides `/dev/ttyUSB0`. Add yourself to the `dialout` group (log out and in).
2. Use `--port /dev/ttyUSB0`. For a faster poll rate set the low-latency flag:
   `echo 1 | sudo tee /sys/bus/usb-serial/devices/ttyUSB0/latency_timer`.
3. The D2XX path is Windows only in this release.

macOS is untested.

Keep the laptop awake (turn off sleep) while logging; a sleep mid-session drops the connection, and the tool will not
reconnect by itself.
