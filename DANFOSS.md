# Danfoss Ally™ eTRV (eTRV0103) — Feature & Zigbee Reference

Curated from the official *Danfoss Ally™ eTRV Feature Catalogue* (doc
`AU417130778872en-000101`, 55 pp). This is the project-relevant subset of
clusters, attributes, and control logic — not a full reproduction. The source
PDF is gitignored.

## Expected operation (our working model)

This is how we understand the eTRVs to behave and how this automation is meant to
drive them. It's the synthesis of the spec sections below plus what we observed on
the live system; the per-attribute spec details follow further down.

### The valve is driven by a PID loop, not on/off

`PIHeatingDemand` (`0x0201/0x0008`) is the controlled output — the **% the valve
is open** (0–100). The eTRV computes it from a PID loop, and HA/ZHA *derives*
`hvac_action` from it: **`0% → idle`, `>0% → heating`**. There is no separate
"idle mode" — idle simply means the PID currently asks for 0%.

Because the loop is anticipatory (§2.6), the valve **does not snap shut the moment
the room passes setpoint**. It holds a residual opening to brake against a
predicted temperature drop. So seeing a small demand (e.g. 1%) with the room a few
degrees — or even many degrees — above setpoint is **expected, not a fault**.

### Reaching idle (0%)

Demand settles to 0% only when the PID concludes no heat is needed for a sustained
period *and* its anticipatory terms have wound down. From the live data, the
decisive factor was **whether an external room sensor is being fed**:

- **No external sensor** (e.g. Stairwell — virtual sensor `unavailable`): standard
  internal estimation; the loop settled cleanly to **0% / idle**.
- **External sensor fed** (the other rooms): engages the active control path
  (§2.3 automatic-offset or §2.4 covered-radiator algorithm), which holds the
  small anticipatory demand even well above setpoint — we saw a steady **1%** on
  all externally-fed TRVs, including the Kitchen at +12.7 °C above setpoint.

Levers that influence (but do not guarantee) wind-down: the control scale factor
`0x0204/0x4020` (5 min "Quick" … 80 min "Slow") and a completed Adaptation Run
(valve characteristic found). There is **no documented minimum-opening floor** —
the steady 1% is the loop's residual output, not a constant.

### "off" is 5 °C anti-freeze — and it does NOT stop the leak

These eTRVs have no true power-off. Setting the HA climate entity to `off` (or
`hvac_mode: off`) does **not** change `system_mode` — the mode stays `heat` and the
device simply drives the **setpoint to ~5 °C (anti-freeze)**. Writing
`SystemMode = 0` is not honored (verified: across many attempts the state never
once became `off`).

Critically, **5 °C frost alone does not close an externally-fed valve** — observed
live, all externally-fed TRVs held `pi_heating_demand = 1` even at a 5 °C setpoint
with the room 17 °C above it. The anticipatory floor comes from the external-sensor
control path, not from the setpoint.

### What actually closes the valve: remove the external sensor feed

The reliable lever is to stop feeding the external room sensor (`0x4015 = -8000`).
The eTRV then controls on its internal sensor and idles (0 %) once the room is
above setpoint — exactly the Stairwell behavior. **This is the summer mechanism**
(`update_heating_season`): disable external sensors above 18 °C outdoor, resume
below 16 °C, with the 16–18 °C band left unchanged (hysteresis), driven by
`sensor.vicare_outside_temperature`. Setpoints are left to the user/schedule.

Caveat: with the external sensor off, a valve will still open if the room drops
below its setpoint (e.g. a cool summer morning against a winter setpoint). In
practice the user's summer "off" (5 °C) setpoints keep rooms well above setpoint,
so valves stay closed.

### How this automation drives the eTRVs

- **Room temperature feed** — every 5 min we push a weighted room temperature into
  each TRV's external room sensor (`0x4015`). When a room has no external sensor —
  or in summer mode — we write `-8000` to disable the feature so the eTRV falls
  back to its internal estimate (sparing radio/battery too, ≈650 msgs/day, §1.1).
- **Seasonal external-sensor toggle** — `update_heating_season` as above.
- **Config maintenance** — weekly: time sync (`0x000A`), `Radiator Covered`
  (`0x4016`, from device label → selects §2.3 vs §2.4), and load balancing disabled
  (`0x4032`, since every room here has a single TRV).

### Operational gotchas we hit

- **Sleepy device:** eTRVs are battery end-devices with a ~5 min wake (check-in)
  interval. A single direct write to a sleeping eTRV fails — every write goes
  through `queue_zigbee_write`, which retries with exponential backoff until it
  lands during a wake window. One-shot REST/service calls are *not* reliable.
- **Manufacturer code only for `0x4000+`:** Danfoss manufacturer-specific
  attributes (`0x4015/0x4016/0x4032/…`) require the manufacturer code; **standard**
  ZCL attributes (Time `0x0000`, SystemMode `0x001C`, setpoint, demand) must be
  accessed *without* it, or zigpy raises `KeyError(manufacturer_code)`.
- **Adaptation Run** (§1.6) occasionally makes a radiator warm for 15–30 min
  (typically at night) while it relearns the valve characteristic — normal, don't
  treat as a fault, and don't inhibit heat while `AdaptationRunStatus = 1`.
- **Critical-low battery (E15)** forces the valve *open* as a frost failsafe —
  rule batteries out before debugging control logic.

## Key fact: the eTRV is a PID controller, not a simple bang-bang thermostat

`PIHeatingDemand` (`0x0201 / 0x0008`) = **% of valve opening**. The eTRV runs a
PID loop and applies *anticipatory* control: it may request heat (open the valve
a few %) **even when the room is already at/above setpoint**, to brake against a
predicted temperature drop. This is documented, expected behavior — not a fault.

### §2.6 Inhibit Heat Request (controller responsibility)

> The eTRV might request the boiler to start even if the comfort temperature is
> reached (… like braking with a car before hitting the actual obstacle).

The **gateway/controller** (i.e. this automation) is responsible for suppressing
the spurious heat request:

> Ignore heat request from eTRV when **all** of the below are true:
> - `RoomTemperature > RoomSetpoint` (add hysteresis to prevent toggling)
> - `AdaptationRunStatus (0x404D) ≠ 1` (don't inhibit during an adaptation run)
>
> RoomTemperature may be `LocalTemperature (0x0000)` or the external room sensor
> value. Room setpoint may be `OccupiedHeatingSetpoint` or the room-sensor setpoint.
> Note: inhibiting deprives the PID of authority and can reduce control accuracy.

**To fully stop heating (e.g. summer): set `system_mode = off`** — this halts the
PID entirely and is cleaner than inhibiting individual heat requests.

## External room sensor — two distinct modes (selected by Radiator Covered)

External room temperature is fed via `0x0201 / 0x4015` (External Measured Room
Sensor), in 0.01 °C units. Value `-8000` disables it (eTRV reverts to internal
estimation). The behavior depends on `Radiator Covered` (`0x0201 / 0x4016`):

| Mode | `0x4016` | Update cadence | Behavior |
|------|----------|----------------|----------|
| **§2.3 Automatic Offset** (exposed radiators) | `FALSE` | ≥ every 3 h, ≤ every 30 min @ 0.1 K change; **disabled after 3 h** of silence | External value derives a dynamic **±4 K offset** to the eTRV's own measurement. eTRV still controls on its (offset-corrected) internal reading. |
| **§2.4 Covered Radiators** (behind cover/curtain/furniture) | `TRUE` | ≥ every 30 min, ≤ every 5 min @ 0.1 K change; **disabled after 35 min** of silence | External value **directly drives the control algorithm**. Window-open detection is disabled in this mode. |

Constraints (both modes): the external sensor **must be in the same room** as the
eTRV (hallway sensor + bedroom eTRV is NOT valid). Feeding an external sensor
engages the active PID path that produces the anticipatory heat demand above —
which is why externally-fed TRVs show `pi_heating_demand > 0` while a TRV with no
external sensor may sit at 0%.

## Zigbee clusters & attributes used by / relevant to this project

### Time — cluster `0x000A`
| Attr | Name | Notes |
|------|------|-------|
| `0x0000` | Time | Seconds since 2000-01-01 00:00:00 UTC. Required; schedule & valve adaptation timing depend on it. |
| `0x0001` | TimeStatus | Write with bit 1 set (`0x02`). |
| `0x0002`–`0x0005` | TimeZone / DstStart / DstEnd / DstShift | Set for locale; refresh DstStart/End yearly before DST. |

eTRV loses time on battery change / OTA / reset. Check `SW Error code` bit 10
(see diagnostics) on (re)join to know if time must be rewritten.

### Thermostat — cluster `0x0201`
| Attr | Name | Notes |
|------|------|-------|
| `0x0000` | LocalTemperature | eTRV's own estimated room temp. |
| `0x0008` | **PIHeatingDemand** | **% valve opening** (0–100). |
| `0x0012` | OccupiedHeatingSetpoint | Active setpoint, 0.01 °C. |
| `0x0015` / `0x0016` | Min/Max Heating Setpoint Limit | Adjustable user limits. |
| `0x0025` | Programming operation mode | bit0 = schedule on/off (0 = manual, aim at OccupiedHeatingSetpoint); bit1 = preheat on/off. |
| `0x4012` | Mounting mode active | 0 = mounted, 1 = not mounted (post factory reset). |
| `0x4015` | External Measured Room Sensor | See external-sensor table above. `-8000` disables. |
| `0x4016` | Radiator Covered | FALSE = exposed (offset mode), TRUE = covered mode. |
| `0x4032` | Load Balancing Enable | Default TRUE. **Disable for single-eTRV rooms.** |
| `0x4040` | Load Radiator Room Mean | GW-computed room load avg, pushed every 15 min. `-8000` = invalid/disable. |
| `0x404A` | Load estimate on this radiator | Per-eTRV load report for load balancing. |
| `0x404B` | Regulation SetPoint Offset | ±2.5 K offset to PID setpoint (range −25..+25 = −2.5..+2.5 °C). Display unchanged. |
| `0x404D` | Adaptation Run Status | bit0 = run in progress, bit1 = success/valve char found, bit2 = char lost/invalid. |

#### Setpoint command (`SetpointCommand`, type byte + 16-bit setpoint)
- `0` Schedule Change — updates OccupiedHeatingSetpoint, no special reaction.
- `1` User Interaction — updates setpoint **and triggers aggressive actuator reaction** (mimics turning the dial). **Cancels an in-progress Adaptation Run.**
- `2` PreHeat — changes only the internal control setpoint; not shown on display.

### Load Balancing (§2.2) — single-eTRV rooms must disable
Distributes heat load between **2+ radiators in the same room**. GW averages each
eTRV's `0x404A` (discarding values < −500 down to −8000, and values > 90 min old)
and pushes the mean via `0x4040` every 15 min. **Must NOT be used in rooms with
only one eTRV.** If the mean isn't sent for > 90 min the eTRV reverts to normal.

### Valve Adaptation Run (§1.6)
Automatic, default ON. Finds the valve characteristic. A User-Interaction setpoint
(type 1) cancels it. While running (`0x404D` bit0 = 1) the valve moves fully —
expected; do not treat as a fault, and don't inhibit heat during it (see §2.6).

### Radio / battery (§1.1)
Battery-powered sleepy end-device. Check-in (wake) interval default **5 min**
(`0x0020 / 0x0000`, in quarter-seconds; 1200 = 5 min). Budget ~650 radio msgs/day.
**Implication: writes only land during a wake window — single one-shot writes to a
sleeping eTRV fail. Use a retry queue.**

### Diagnostics — cluster `0x0B05`
| Attr | Name | Notes |
|------|------|-------|
| `0x4000` | SW Error code | Bitfield. Bit 10 = time lost → rewrite Time cluster. |
| `0x011C` | LastMessageLQI | Link quality of last message. |
| `0x4010` | Motor step counter | Lifetime accumulated motor steps. |

Battery via Power cluster `0x0001 / 0x0021` BatteryPercentageRemaining (0–200).

#### Error codes of note
- **E13 Encoder Jammed**, **E14 Low Battery** (replace ASAP).
- **E15 Critical Low Battery** — *"The eTRV cannot control the valve longer and has
  opened the valve to prevent potential frost damages."* → a near-dead battery
  **forces the valve open**. Rule this out before debugging control logic.

### Open-window detection (`0x0201 / 0x4000`)
0x00 Quarantine, 0x01 Closed, 0x02 maybe opening, 0x03 open detected, 0x04 open
from external but locally closed. Disabled in Covered Radiator mode.

## How this maps to the current automation (`danfoss.py`)

- `set_time()` → Time cluster `0x000A` (weekly + on join, per §1.2).
- `radiator_covered()` → `0x4016` from device label (selects §2.3 vs §2.4 mode).
- `disable_load_balancing()` → `0x4032 = FALSE` (correct: single-eTRV rooms).
- `update_external_temperatures()` → `0x4015` (room temp, or `-8000` to disable).
  Skips TRVs currently in `off` mode to save radio/battery (§1.1).
- `update_heating_season()` → `system_mode` (`0x001C`): off above 18 °C outdoor,
  heat below 16 °C (hysteresis band in between), driven by
  `sensor.vicare_outside_temperature`. This is what addresses the persistent
  summer `pi_heating_demand = 1` — turning the eTRV off halts the anticipatory
  PID demand entirely (cleaner than the §2.6 heat-request inhibit).
