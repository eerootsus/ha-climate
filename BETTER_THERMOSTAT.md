# Migration plan: Better Thermostat as the controller

## Why we're moving

The Danfoss eTRV's **native external room sensor** feature gives accurate
room-based control but holds an anticipatory ~1 % valve opening that never fully
closes (see `DANFOSS.md` — the PID floor, observed year-round on every
externally-fed TRV; only the one TRV *without* an external sensor idles at 0 %).
With this firmware you cannot have both accurate external-sensor control **and** a
fully-closing valve. So we hand control to **Better Thermostat (BT)** and use each
eTRV as a calibrated actuator instead.

## Target architecture

```
weighted room sensors (danfoss.py)  ──►  Better Thermostat (per room)  ──►  eTRV
sensor.climate_<area>_temperature        target temp + calibration            (actuator)
                                          outdoor threshold (summer off)
```

- **danfoss.py is now sensor-aggregation only:** `update_room_climate_sensors`
  publishes the weighted `sensor.climate_<area>_temperature` (BT's per-room input)
  plus its helpers. **All TRV writes were removed** (time sync, radiator-covered,
  load-balancing, external-sensor feed, retry queue) so it cannot fight BT.
- **eTRV native external sensor is turned OFF** so it doesn't fight BT:
  `prioritize external temperature sensor = off` and external sensor = `-8000`
  (done on all TRVs).

## Per-room mapping

| Room | eTRV climate entity | BT external sensor input |
|------|---------------------|--------------------------|
| Ada | `climate.trv_danfoss_ada` | `sensor.climate_ada_s_room_temperature` |
| Master/Bedroom | `climate.trv_danfoss_master_thermostat_4` | `sensor.climate_bedroom_temperature` |
| Kitchen | `climate.trv_danfoss_kitchen_thermostat_5` | `sensor.climate_kitchen_temperature` |
| Lola | `climate.trv_danfoss_lola` | `sensor.climate_lola_s_room_temperature` |
| Stairwell | `climate.trv_danfoss_stairwell_thermostat_3` | (no external sensor — TRV internal only) |

## Setup steps

1. **Install Better Thermostat** via HACS (Integrations → Better Thermostat), then
   restart HA.
2. **Disable the eTRV native external sensor** on every TRV so BT has sole control:
   `switch.*prioritize_external_temperature_sensor` → off and external = `-8000`.
   (Already done on all five; danfoss.py no longer pushes `0x4015`.)
3. **Add a Better Thermostat** per room (Settings → Devices & Services → Add →
   Better Thermostat) with:
   - **Thermostat:** the eTRV climate entity (table above)
   - **Temperature sensor:** the room's `sensor.climate_<area>_temperature`
   - **Outdoor sensor:** `sensor.vicare_outside_temperature` + outdoor threshold
     (e.g. 18 °C) → this is the summer-off mechanism, replacing `update_heating_season`
   - **Calibration type:** **Target Temperature Based** (Danfoss's offset is capped
     at ±2.5 K — too small; let BT drive the setpoint instead)
   - **Algorithm:** start **Normal**; revisit AI Time Based / PID later
   - **Window sensors:** optional; if used, disable the eTRV's own open-window
     detection to avoid double-handling
   - **Tolerance:** small (e.g. 0.3 °C) to limit valve cycling
4. **Verify:** with a room above target, BT should drive the eTRV to its off/5 °C
   state and `pi_heating_demand` should reach **0** (the thing native mode never did).

danfoss.py has already been trimmed to sensor-aggregation only — no further code
changes needed for the cutover.

## Firmware & config baseline (verified)

- **Firmware is already uniform and current:** all five report
  `sw_version = 0x00000020`, and every `update.*_firmware` entity is `off`
  (installed == latest). **No OTA update is needed or available** — don't chase one.
- The differing entity names (EN "prioritise" / EN "prioritize" / Estonian for
  Stairwell, plus extra `heat_available`/pre-heat entities on Lola & Ada) are **ZHA
  quirk/locale variants at pairing time, not firmware** — cosmetic, no behavioural
  effect. Re-interviewing a device *may* normalize names but is unnecessary.
- **Behavioural config is unified across all five:** `prioritize external = off`,
  external sensor = `-8000`, load balancing off, min/max 5/35, valve orientation
  Horizontal, setpoint response "quick 5min", valve exercise Thu 11:00, adaptation
  enabled.
- **Watch item:** Lola's Zigbee link is weak (`lqi`/`rssi` unknown; writes needed
  several retries). Improve placement / add a nearby router so BT commands land.
- **Note:** the eTRV clock is no longer synced by this project (set_time was
  removed). It only affects valve-exercise/adaptation timing, not BT control; sync
  once manually via ZHA if desired.

## Status

- **Kitchen** BT created and healthy (`climate.kitchen_better_thermostat`): reads
  `sensor.climate_kitchen_temperature`, no errors, target driven to 5 °C, BT idle.
  Confirming the underlying valve reaches `pi_heating_demand = 0` (sleepy-device
  lag; Stairwell with identical config already idles, so it should follow).
- Remaining rooms (Ada, Master, Lola) to be added via the UI flow (config-flow
  integrations can't be created via the REST API). Stairwell: optional — it has no
  external sensor and already idles natively.

## Sources
- Better Thermostat docs — https://better-thermostat.org/configuration
- Danfoss Ally external-sensor calibration writeup — https://ha-praksis.dk/en/case-calibrating-danfoss-ally-with-external-temperature-sensors/
- Danfoss Ally firmware archive (v1.28/v1.20/v1.18/v1.08), ZHA/deCONZ/Z2M —
  https://community.home-assistant.io/t/danfoss-ally-thermostat-firmware-archive-v1-28-v1-20-v1-18-v1-08-specifications-zha-deconz-zigbee2mqtt/261951
