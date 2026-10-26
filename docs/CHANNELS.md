# Channel map

Every request address, decoded column, unit, scale, **confidence** and the vehicle evidence behind it.
The tables below are generated from `delica_mut/channels.py` (a test keeps them in sync); edit the code, then
run `python -m delica_mut.channels gearbox` / `engine` to refresh them.

## Attribution and what is not included

Channel names and scales were cross-checked against the MMC-Reader diagnostic database and then compared with
recordings from a real 1999 Delica Space Gear 4M40 EFI (automatic). **This project is not affiliated with
MMC-Reader.** Only the resulting facts are published here: address, name, unit, scale or offset, confidence and our
own evidence notes. Not copied: MMC-Reader database files, raw tables, lookup tables or fault-description texts.

## Confidence legend

| Level | Meaning |
| --- | --- |
| high | the formula agrees with controlled behaviour on the van (pedal pressed or released, A/C cycling, revs, gears) |
| medium | consistent with the van, but no independent reference (meter, GPS, tachometer, probe) |
| low | the formula comes from the profile only; the quantity was never verified |
| unverified | documented, but the input was never exercised (switch never pressed) |
| provisional | fitted curve, about +/-3 C, independent calibration pending |

"Calibrated" is deliberately not on this list: nothing here was calibrated against instruments by this project.

## Gearbox computer (diagnostic ID F3 06)

Wake-up: address 0x01, keywords `70 85`. Requests 00-BF are read-only. Values are the latest sample of each request;
the `fresh` column of the CSV says which requests were actually read in that cycle.

<!-- BEGIN GEARBOX TABLE -->
| Request | Column | Name | Unit | Formula | Confidence | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | engine_rpm | Engine speed (crank angle sensor) | rpm | raw x 50 | high | 0 engine-off; tracks revs; within ~11 rpm of 30 x raw 20 over 4378 drive samples |
| 11 | input_rpm | Input shaft (turbine) speed | rpm | raw x 30 | high | 0 when stopped in D, follows engine in N/P, follows output speed by gear ratio |
| 12 | output_rpm | Output shaft speed | rpm | raw x 30 | high | 0 in every parked capture; gear-dependent ratio to input speed |
| 13 | atf_C | ATF temperature | C | raw - 40 | medium | 27 C engine-off, 31-33 C warm-up, 62-68 C on the drive; no probe reference |
| 14 | pedal_V | Accelerator pedal sensor | V | raw / 51.2 | high | 0.88 V released, 2.93 V held in parked tests; voltage not meter-checked |
| 15 | theo_pressure | Theoretical pressure (not a measured pressure) | kPa | raw x 9.18 - 588 | low | profile quantity only; can be negative; do not clamp |
| 16 | shift_pos | Shift position |  | lookup | high | 73/73 fresh drive samples agree with gear from shaft ratios |
| 18 | dcc_slip_rpm | Damper clutch (lock-up) slip | rpm | raw - 51 (raw 0 / 255 saturate) | high | matches 50 x raw10 - 30 x raw11 within 50 rpm in 2129/2149 unsaturated samples |
| 1A | dcc_duty_pct | Damper clutch (lock-up) solenoid duty | % | raw / 2.55 | medium | 99 % locked and 0 % released in drive 1; no electrical measurement |
| 1B | sol_2nd_pct | Secondary (2nd) solenoid duty | % | 100 - raw / 2.55 | low | profile only; varies with operating state |
| 1D | sol_LR_pct | Low and reverse solenoid duty | % | 100 - raw / 2.55 | low | profile only; varies with operating state |
| 1E | sol_OD_pct | Overdrive solenoid duty | % | 100 - raw / 2.55 | low | profile only; varies with operating state |
| 1F | sol_UD_pct | Underdrive solenoid duty | % | 100 - raw / 2.55 | low | profile only; varies with operating state |
| 27 | inhibitor | Inhibitor (selector) switch |  | lookup | medium | 1 in every parked capture, 1/2/16 on the drive; no labelled selector test |
| 28 | *flags_28* | Switch flags | bits | bit masks | | |
| 28 | brake | Brake (stop lamp) switch | 0/1 | mask 01 | high | matches an independent brake bit in 512/515 parked cycles |
| 28 | hold_sw | STD/HOLD switch | 0/1 | mask 02 | unverified | never exercised |
| 28 | tf_low | Transfer low (T/F) switch | 0/1 | mask 08 | unverified | never exercised |
| 28 | idle_pos | Idle position (pedal released) (active low) | 0/1 | mask 20 | high | clears with pedal released, sets on pedal, 24/24 and 40/40 fresh samples |
| 28 | od_off_sig | O/D OFF signal | 0/1 | mask 40 | unverified | never exercised |
| 28 | ac_relay | A/C relay (active low) | 0/1 | mask 80 | high | follows A/C compressor cycling in the parked test |
| 2A | elc_relay_V | ELC relay voltage | V | raw / 7.69 | medium | 12.1 V engine-off, higher running; relay-circuit voltage, not a battery-terminal reading |
| 2B | *flags_2B* | Switch flags 2 | bits | bit masks | | |
| 2B | od_off_sw | O/D OFF switch | 0/1 | mask 04 | unverified | never exercised |
| 44 | speed_kmh | Vehicle speed | km/h | raw x 2.8 | medium | 0 parked; follows output shaft; 0-89.6 km/h on the drive; no GPS reference |
| 96 | fault_96 | A/T fault slot 1 | hex | hex byte (00/FF = none) | low | all slots empty in every recording; raw byte only, no descriptions |
| 97 | fault_97 | A/T fault slot 2 | hex | hex byte (00/FF = none) | low | all slots empty in every recording; raw byte only, no descriptions |
| 98 | fault_98 | A/T fault slot 3 | hex | hex byte (00/FF = none) | low | all slots empty in every recording; raw byte only, no descriptions |
| 99 | fault_99 | A/T fault slot 4 | hex | hex byte (00/FF = none) | low | all slots empty in every recording; raw byte only, no descriptions |
| 9A | fault_9A | A/T fault slot 5 | hex | hex byte (00/FF = none) | low | all slots empty in every recording; raw byte only, no descriptions |
| 9B | fault_9B | A/T fault slot 6 | hex | hex byte (00/FF = none) | low | all slots empty in every recording; raw byte only, no descriptions |
| 9C | fault_9C | A/T fault slot 7 | hex | hex byte (00/FF = none) | low | all slots empty in every recording; raw byte only, no descriptions |
| 9D | fault_9D | A/T fault slot 8 | hex | hex byte (00/FF = none) | low | all slots empty in every recording; raw byte only, no descriptions |
<!-- END GEARBOX TABLE -->

Notes:

- `dcc_slip_rpm` saturates: raw 0 and raw 255 are shown as -51 and 204 with `dcc_slip_sat` = `lo` / `hi`. Treat those as
  "at least", not exact values.
- `theo_pressure` is a profile quantity ("theoretical pressure"), not a measured hydraulic or fuel pressure. It can be
  negative; it is not clamped.
- `elc_relay_V` is the relay-circuit voltage reported by the computer, not a battery-terminal reading.
- `atf_C` is the transmission fluid temperature, not coolant.
- Solenoid duties (`sol_*`) and `dcc_duty_pct` are what the computer commands, not electrical measurements.
- Fault slots 96-9D are raw bytes (`00` and `FF` mean none). No descriptions are shipped; use your service manual.

## Engine computer (diagnostic ID 3002)

Wake-up: address 0x00, keywords `EF 85`, 10 s quiet line first. **Only** the 31 requests below are ever sent (plus FE/FF
and the one-shot ROM-ID reads 80/81/82). See [SAFETY.md](SAFETY.md).

<!-- BEGIN ENGINE TABLE -->
| Request | Column | Name | Unit | Formula | Confidence | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | boost_air_C | Boost air temperature | C | Steinhart-Hart curve or user table | provisional | provisional: Steinhart-Hart curve (about +/-3 C) fitted to the MMC-Reader diagnostic database conversion; matched this project's van at engine-off (coolant 43 C, boost-air 43 C, fuel 38 C); independent on-vehicle calibration pending |
| 11 | coolant_C | Coolant temperature | C | Steinhart-Hart curve or user table | provisional | provisional: Steinhart-Hart curve (about +/-3 C) fitted to the MMC-Reader diagnostic database conversion; matched this project's van at engine-off (coolant 43 C, boost-air 43 C, fuel 38 C); independent on-vehicle calibration pending |
| 12 | baro_kPa | Barometric pressure | kPa | raw / 2.03 + 0.3 | medium | 100.3 kPa engine-off; plausible; no reference |
| 13 | boost_kPa | Boost pressure sensor (absolute) | kPa | raw x 1.33 | medium | 99.75 kPa engine-off and near ambient at idle; under-load boost not yet recorded |
| 14 | fuel_C | Fuel temperature | C | Steinhart-Hart curve or user table | provisional | provisional: Steinhart-Hart curve (about +/-3 C) fitted to the MMC-Reader diagnostic database conversion; matched this project's van at engine-off (coolant 43 C, boost-air 43 C, fuel 38 C); independent on-vehicle calibration pending |
| 15 | speed_kmh | Vehicle speed | km/h | raw | unverified | 0 in every (parked) engine recording; not yet driven |
| 16 | rpm_backup | Engine speed (backup) | rpm | raw x 25 | medium | tracks the primary speed signal |
| 17 | rpm | Engine speed | rpm | raw x 25 | high | 750-900 rpm at idle, matching the observed idle |
| 18 | pedal_V | Accelerator pedal sensor | V | raw / 51 | high | 0.88 V released, 3.47-3.51 V held |
| 19 | pedal_pct | Accelerator pedal position | % | raw / 2.56 | medium | 0 % released at idle |
| 1A | battery_V | Battery voltage | V | raw / 13.64 | medium | 12.8 V key-on, 13.6-14.2 V running |
| 1C | tcv_duty_pct | Timing control valve duty | % | raw / 2.5 | low | profile only |
| 1D | egr_target_pct | Target EGR | % | raw / 2.5 | low | profile only |
| 1E | inj_adjust_V | Injection adjust value | V | raw / 51.2 | low | profile only; 2.5 V at mid-scale raw 128 |
| 20 | sleeve_target_pct | Control sleeve position target | % | raw / 2.56 | medium | moves with load; sequential reads cannot resolve fast tracking |
| 21 | timing_actual_CA | Injection timing actual | deg CA | raw / 5 | medium | actual generally followed target at idle (profile also offers % and V views of the same byte) |
| 22 | timing_target_CA | Injection timing target | deg CA | raw / 5 | medium | see actual timing |
| 24 | ge_duty_pct | GE actuator duty | % | raw / 2.56 | low | profile only |
| 25 | egr_duty_pct | EGR duty | % | raw / 2.56 | low | profile only |
| 26 | sleeve_actual_pct | Control sleeve position actual | % | raw / 2.56 | medium | varies more during rough running; sequential reads |
| 00 | *switches_00* | Switch byte 00 | bits | bit masks | | |
| 00 | idle_sw1 | Idle switch 1 | 0/1 | mask 40 | low | read Off with the pedal released on the test van while fault 23 (idle switch 1) was set; treat as suspect |
| 00 | idle_sw2 | Idle switch 2 | 0/1 | mask 10 | medium | Off with pedal held, On when released |
| 00 | ac_sw | A/C switch | 0/1 | mask 04 | unverified |  |
| 00 | st_sw | Starter (ST) switch | 0/1 | mask 01 | unverified |  |
| 01 | *switches_01* | Switch byte 01 | bits | bit masks | | |
| 01 | ig_sw | Ignition switch | 0/1 | mask 40 | low |  |
| 01 | control_relay | Control relay | 0/1 | mask 10 | low |  |
| 01 | ac_relay | A/C relay | 0/1 | mask 04 | unverified |  |
| 02 | *switches_02* | Switch byte 02 | bits | bit masks | | |
| 02 | fan_relay_lo | Fan relay LO | 0/1 | mask 10 | unverified |  |
| 02 | glow_relay | Glow plug relay | 0/1 | mask 01 | low |  |
| 03 | *switches_03* | Switch byte 03 | bits | bit masks | | |
| 03 | throttle_sol | Throttle valve solenoid | 0/1 | mask 40 | low |  |
| 03 | throttle_sol2 | Throttle valve solenoid 2 | 0/1 | mask 10 | low |  |
| 03 | check_lamp | Engine check lamp | 0/1 | mask 04 | low |  |
| 03 | glow_lamp | Glow lamp | 0/1 | mask 01 | low |  |
| 04 | *switches_04* | Switch byte 04 | bits | bit masks | | |
| 04 | neutral_sw | Neutral switch | 0/1 | mask 10 | unverified |  |
| 04 | abs_sw | ABS switch | 0/1 | mask 04 | unverified |  |
| 04 | fuel_cut_valve | Fuel cut valve | 0/1 | mask 01 | low |  |
| 05 | *switches_05* | Switch byte 05 | bits | bit masks | | |
| 05 | egr_sol2 | EGR solenoid 2 | 0/1 | mask 40 | low |  |
| 05 | is_at | Automatic transmission (set = A/T) | 0/1 | mask 10 | low |  |
| 05 | is_van | Vehicle type (set = van) | 0/1 | mask 04 | low |  |
| 06 | *switches_06* | Switch byte 06 | bits | bit masks | | |
| 06 | coolant_temp_sw | Coolant temperature switch | 0/1 | mask 40 | unverified |  |
| 06 | ac_temp_signal | A/C temperature signal | 0/1 | mask 10 | unverified |  |
| 06 | intercooler_fan | Intercooler fan | 0/1 | mask 04 | unverified |  |
| 50 | fault_50 | Fault bit byte 50 | hex | hex byte, bit = one fault | low | no bits set in recordings; look the bits up in your service manual |
| 51 | fault_51 | Fault bit byte 51 | hex | hex byte, bit = one fault | high | bit 04 = blink code 23 (idle switch 1) on the test van |
| 52 | fault_52 | Fault bit byte 52 | hex | hex byte, bit = one fault | low | no bits set in recordings; look the bits up in your service manual |
| 53 | fault_53 | Fault bit byte 53 | hex | hex byte, bit = one fault | low | no bits set in recordings; look the bits up in your service manual |
<!-- END ENGINE TABLE -->

Notes:

- `boost_kPa` is an absolute pressure (it reads about ambient at idle); `boost_gauge_kPa` is derived as `boost_kPa - baro_kPa`.
- The profile offers three views of the injection timing bytes (21/22): degrees CA, percent and volts. This project shows
  degrees CA (`raw / 5`). The other two are the same byte divided by 2.56 or 51.
- Both engine pedal channels exist: 18 (volts) and 19 (percent). 19 stayed at 0 % while 18 read the idle voltage (0.84 to 0.88 V) on the test van.
- Fault bytes 50-53 are raw. Example from the test van: byte 51 = `04` was set while the check-engine light blinked code 23
  (idle switch 1). Look other bits up in your service manual; no descriptions are shipped.

### Engine temperature channels (10 boost air, 11 coolant, 14 fuel): provisional

provisional: Steinhart-Hart curve (about +/-3 C) fitted to the MMC-Reader diagnostic database conversion; matched this project's van at engine-off (coolant 43 C, boost-air 43 C, fuel 38 C); independent on-vehicle calibration pending.

How it works:

- No lookup table is shipped. Each channel uses a three-coefficient Steinhart-Hart style curve:
  `x = raw (valid 4..251)`, `r = x / (255 - x)`, `L = ln(r)`, `T = 1 / (a + b*L + c*L^3) - 273.15`.
- Results outside the fitted range (-20 to 110 C) or raw bytes outside 4..251 are shown as empty; the raw byte
  is always kept in `coolant_raw`, `boost_air_raw`, `fuel_raw`.
- Fit error against the source conversion: up to about 2.5 C (coolant), 3.0 C (boost air), 3.4 C (fuel). Engine-off values
  on the test van were 43 C coolant, 43 C boost air and 38 C fuel.
- This project did not perform a temperature calibration. Until you check against a thermometer, treat the values as an
  estimate that is good for trends (warm-up, heat soak), not for diagnosis at a single degree.

**Supply your own table.** Create `temperature_tables.json` (in the folder you run from, in
`~/.delica-4m40-diag/`, or point to it with `--temp-tables FILE` or the `DELICA_TEMP_TABLES` environment variable):

```json
{
  "coolant_C":   [ ...256 numbers, index = raw byte 0..255, null = no reading... ],
  "boost_air_C": [ ... ],
  "fuel_C":      [ ... ]
}
```

Any of the three keys may be left out; those channels keep the curve. A key must hold exactly 256 entries. A user table
always wins over the curve, and the dashboard says so ("user table"). `delica-decode --raw-temps` and the dashboard checkbox
"temperatures as raw bytes" show the raw byte only.

## Decoded CSV columns

`delica-decode` writes `time, utc_ms, elapsed_s, marker`, then every column above in table order (bit rows become 0/1
columns; 1 means active, so `idle_pos` = 1 when the pedal is released and `ac_relay` = 1 when the relay is on), then `fresh`.
