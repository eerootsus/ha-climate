# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HA Climate is a Home Assistant PyScript automation for managing Danfoss eTRV0103 Zigbee thermostatic radiator valves (TRVs). It creates virtual room climate sensors with weighted averaging from multiple TRVs and external sensors.

## Setup & Deployment

This is not a standalone Python project - it runs within Home Assistant's PyScript integration.

**Installation:**
1. Copy `danfoss.py` to `config/pyscript/`
2. Copy `trv-climate/climate.yaml` to `config/trv-climate/`
3. Include in `configuration.yaml`:
   ```yaml
   homeassistant:
     packages:
       climate_sensors: !include trv-climate/climate.yaml
   ```
4. Restart Home Assistant

No build step required. Dependencies in `requirements.txt` are Home Assistant's own packages.

## Architecture

**danfoss.py** - Main PyScript module containing:

- **Device Management**: Functions to retrieve TRV devices from HA registries, find associated climate/sensor entities, and convert to ZHA Zigbee devices
- **Weighted Calculation**: `calculate_weighted_climate()` computes area averages where TRVs have weight 0.5 and external sensors use device label weights (e.g., `sensor_weight_2`)
- **Scheduled Tasks** (PyScript time_trigger decorators):
  - `set_time()` - Weekly time sync to TRV Zigbee cluster
  - `radiator_covered()` - Weekly check/update of radiator obstruction attribute based on device labels
  - `update_room_climate_sensors()` - Every 5 min, creates virtual `sensor.climate_{area_id}_{type}` entities
  - `update_external_temperatures()` - Pushes virtual sensor values back to TRV external sensor attribute

**trv-climate/climate.yaml** - Template sensor definitions wrapping pyscript-created sensors for proper HA UI management.

## Key Zigbee Constants

```python
CLUSTER_TIME = 0x000A           # Time cluster
CLUSTER_THERMOSTAT = 0x0201     # Thermostat cluster
ATTR_RADIATOR_COVERED = 0x4016  # Manufacturer-specific
ATTR_EXTERNAL_MEASURED_ROOM_SENSOR = 0x4015
```

## Device Labels

Configure in Home Assistant UI on devices:
- `radiator_covered` - Mark TRVs behind furniture/curtains
- `sensor_weight_X` - External sensors with weight X for averaging

## Adding New Areas

Areas are auto-detected from HA device assignments. Add corresponding template sensors to `trv-climate/climate.yaml` following existing pattern.
