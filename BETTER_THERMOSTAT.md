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
   set `switch.*prioritize_external_temperature_sensor` → off. (danfoss.py will also
   stop pushing `0x4015`; until that change ships, the 5-min push would re-enable it.)
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

## Firmware normalization (separate track)

The TRVs show three different entity-naming sets (EN "prioritise" / Estonian / EN),
i.e. they were paired at different times on different quirk/firmware versions.
Normalize so they behave identically:

- **Target:** latest **v1.28** (`00.28`). Earlier known: v1.18, v1.08.
- **Process:** ZHA OTA. With an OTA provider configured, an `update.<device>` entity
  appears when an update is available; trigger from there.
- **Caveats:**
  - OTA on battery end-devices is **slow (hours)** and can fail ("Aborted by
    device") — do it with a **fresh/full battery** and the TRV close to the
    coordinator. (Lola is at 15 % + shows a software_error → replace its battery
    first, as planned.)
  - **Downgrades are refused** by the device.
  - Do them one at a time; re-sync time afterwards (FW update invalidates the clock).

## Open question to validate during setup

Whether BT's Target-Temperature-Based calibration on Danfoss closes cleanly to 0 %
in practice (some Danfoss + BT combos need tuning). Confirm on one room (Kitchen)
before rolling out to all five.

## Sources
- Better Thermostat docs — https://better-thermostat.org/configuration
- Danfoss Ally external-sensor calibration writeup — https://ha-praksis.dk/en/case-calibrating-danfoss-ally-with-external-temperature-sensors/
- Danfoss Ally firmware archive (v1.28/v1.20/v1.18/v1.08), ZHA/deCONZ/Z2M —
  https://community.home-assistant.io/t/danfoss-ally-thermostat-firmware-archive-v1-28-v1-20-v1-18-v1-08-specifications-zha-deconz-zigbee2mqtt/261951
