# HA Climate

Pyscript-based climate control for Danfoss TRVs in Home Assistant.

## Features

- Reads temperature from Danfoss eTRV0103 climate entities
- Creates virtual room temperature sensors (weighted average when multiple TRVs per room)
- Supports external temperature sensors with configurable weights (label devices with `sensor_weight_X`)
- Updates TRV external temperature sensors from virtual room sensors
- Syncs time on TRVs (weekly)
- Manages radiator covered attribute based on device labels
- Automatic retry queue for failed Zigbee writes (exponential backoff)

## Home Assistant Setup

### Step 1: Copy Files to HA Config

```
config/
├── pyscript/
│   └── danfoss.py                    <- main pyscript
├── trv-climate/
│   └── climate.yaml                  <- template sensors with unique_ids
└── configuration.yaml
```

### Step 2: Include in configuration.yaml

```yaml
homeassistant:
  packages:
    climate_sensors: !include trv-climate/climate.yaml
```

### Step 3: Restart Home Assistant

Settings → System → Restart

---

## How It Works

### Virtual Temperature Sensors

The pyscript creates virtual sensors (`sensor.climate_{area_id}_temperature`) by:
1. Finding all TRVs assigned to each area
2. Reading `current_temperature` from each TRV's climate entity
3. Calculating weighted average (TRVs have weight 0.5, external sensors use their label weight)
4. Creating virtual sensor entities

The template sensors in `sensors/climate.yaml` wrap these with proper `unique_id` for UI management (area assignment, customization).

### External Temperature Sensors

To add external temperature sensors (e.g., a separate Zigbee sensor):
1. Assign the device to the same area as the TRVs
2. Add a label `sensor_weight_X` where X is the weight (e.g., `sensor_weight_2` for double weight)

### Device Labels

- `radiator_covered` - Sets the TRV's radiator covered attribute (for TRVs behind furniture/curtains)
- `sensor_weight_X` - Includes device's temperature sensor in room average with weight X

### Enable History Graphs for Load Estimates

The TRV load estimate sensors don't have `state_class` set by default, so Home Assistant won't record history. To enable graphs, add to `configuration.yaml`:

```yaml
homeassistant:
  customize:
    sensor.trv_danfoss_ada_load_estimate:
      state_class: measurement
    sensor.trv_danfoss_kitchen_load_estimate:
      state_class: measurement
    sensor.trv_danfoss_lola_load_estimate:
      state_class: measurement
    sensor.trv_danfoss_master_load_estimate:
      state_class: measurement
    sensor.trv_danfoss_stairwell_load_estimate:
      state_class: measurement
```

---

## Scheduled Tasks

| Schedule | Function | Description |
|----------|----------|-------------|
| Startup | `startup` | Runs all init tasks sequentially (avoids Zigbee congestion) |
| Sunday 3:00 AM | `set_time` | Weekly time sync on all TRVs |
| Monday 3:00 AM | `radiator_covered` | Weekly radiator covered attribute check |
| Tuesday 3:00 AM | `disable_load_balancing` | Weekly load balancing disable (for single-TRV rooms) |
| Every 5 min | `update_room_climate_sensors` | Update virtual sensor values |
| Every 5 min | `update_external_temperatures` | Push room temp to TRVs |
| Every 1 min | `process_pending_writes` | Retry failed Zigbee writes |

---

## Zigbee Message Queue

All Zigbee writes go through a retry queue. If a write fails (timeout or error), it's queued for retry with exponential backoff:

| Retry | Delay |
|-------|-------|
| 1 | 1 min |
| 2 | 2 min |
| 3 | 4 min |
| 4 | 8 min |
| 5 | 16 min |
| 6 | 32 min |
| 7 | ~1 hour |
| 8 | ~2 hours |
| 9-10 | 4 hours (max) |

After 10 retries, the write is abandoned and logged as an error.

**Key behaviors:**
- Newer writes for the same device+attribute replace pending ones (stale values discarded)
- Queue is in-memory only (cleared on HA restart)
- Battery-powered TRVs often sleep, causing timeouts—the queue handles this gracefully

**Debug service:** Call `pyscript.get_pending_writes` from Developer Tools → Services to inspect the current queue.

---

## Adding New Areas

When you add TRVs to a new area:

1. The pyscript will automatically create `sensor.climate_{area_id}_temperature`
2. Add a new entry to `trv-climate/climate.yaml`:

```yaml
      - name: "New Room Temperature"
        unique_id: climate_new_room_temperature
        device_class: temperature
        state_class: measurement
        unit_of_measurement: "°C"
        state: "{{ states('sensor.climate_new_room_temperature') }}"
        availability: "{{ states('sensor.climate_new_room_temperature') not in ['unknown', 'unavailable'] }}"
```

3. Reload YAML or restart Home Assistant
