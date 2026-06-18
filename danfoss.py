"""Room climate sensor aggregation for Better Thermostat.

This module's sole job is to publish a weighted virtual temperature/humidity
sensor per area (`sensor.climate_<area_id>_temperature` / `_humidity`) from the
external sensors labelled `sensor_weight_X`, for Better Thermostat to consume as
its per-room temperature input (BT takes a single sensor and does not do weighted
averaging itself).

It deliberately performs NO writes to the TRVs. Heating control — setpoint,
on/off, calibration — is owned entirely by Better Thermostat (see
BETTER_THERMOSTAT.md). The previous Zigbee control logic (time sync, radiator
covered, load balancing, external-sensor feed, retry queue) was removed so this
script can never interfere with what BT controls. See DANFOSS.md for the eTRV
behaviour that led here (§2.6: the native external-sensor feed holds an
anticipatory ~1% valve opening, so it was retired).
"""

from logging import Logger
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry, device_registry, entity_registry
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.components.sensor import SensorDeviceClass

DEVICE_MODEL = "eTRV0103"

LABEL_SENSOR_WEIGHT_PREFIX = "sensor_weight_"


hass: HomeAssistant
log: Logger


def get_all_climate_devices() -> tuple[dict[str, list[DeviceEntry]], dict[str, list[tuple[DeviceEntry, float]]]]:
    """Scan all devices once and return TRVs and weighted devices grouped by area.

    Returns (trv_devices_by_area, weighted_devices_by_area). TRVs are used only to
    determine which areas should get a virtual sensor; the weighted devices provide
    the actual temperature/humidity readings.
    """
    dr = device_registry.async_get(hass)
    trv_devices_by_area: dict[str, list[DeviceEntry]] = {}
    weighted_devices_by_area: dict[str, list[tuple[DeviceEntry, float]]] = {}

    for device_id in dr.devices:
        device: DeviceEntry | None = dr.async_get(device_id)
        if device is None or device.area_id is None:
            continue

        area_id = device.area_id

        # Check if TRV
        if device.model == DEVICE_MODEL:
            if area_id not in trv_devices_by_area:
                trv_devices_by_area[area_id] = []
            trv_devices_by_area[area_id].append(device)

        # Check for weight label
        for label in device.labels:
            if label.startswith(LABEL_SENSOR_WEIGHT_PREFIX):
                try:
                    weight = float(label[len(LABEL_SENSOR_WEIGHT_PREFIX):])
                    if area_id not in weighted_devices_by_area:
                        weighted_devices_by_area[area_id] = []
                    weighted_devices_by_area[area_id].append((device, weight))
                    log.debug(f"Found weighted device {device.name_by_user} ({device.id}) with weight={weight}")
                except ValueError:
                    log.warning(f"Invalid weight label '{label}' on device {device.name_by_user} ({device.id})")
                break

    return trv_devices_by_area, weighted_devices_by_area


def get_climate_entity_for_device(device: DeviceEntry, device_class: SensorDeviceClass) -> str | None:
    """Find entity belonging to device with specified device_class.

    For temperature, also matches climate entities (which expose current_temperature as state).
    Returns entity_id or None.
    """
    er = entity_registry.async_get(hass)

    entries = list(er.entities.get_entries_for_device_id(device.id))
    log.debug(f"Device {device.name_by_user} has {len(entries)} entities")

    for entry in entries:
        # For temperature, climate entities expose current_temperature as their state
        if device_class == SensorDeviceClass.TEMPERATURE and entry.domain == "climate":
            log.debug(f"  {entry.entity_id}: MATCH (climate entity)")
            return entry.entity_id

        if entry.domain != "sensor":
            continue
        if entry.original_device_class != device_class:
            continue

        log.debug(f"  {entry.entity_id}: MATCH")
        return entry.entity_id

    log.debug(f"Device {device.name_by_user}: no {device_class} entity found")
    return None


def get_sensor_value(entity_id: str) -> float | None:
    """Get numeric sensor value, returning None if unavailable.

    For climate entities, reads the current_temperature attribute.
    """
    try:
        state_obj = state.get(entity_id)
    except NameError:
        log.debug(f"Entity {entity_id} does not exist")
        return None

    if state_obj in ("unavailable", "unknown", None):
        log.debug(f"Entity {entity_id} is unavailable or unknown")
        return None

    # Climate entities store temperature in current_temperature attribute
    if entity_id.startswith("climate."):
        try:
            temp = state.getattr(entity_id).get("current_temperature")
            if temp is None:
                log.debug(f"Entity {entity_id} has no current_temperature attribute")
                return None
            return float(temp)
        except (ValueError, TypeError, AttributeError) as e:
            log.warning(f"Entity {entity_id} has invalid current_temperature: {e}")
            return None

    try:
        return float(state_obj)
    except (ValueError, TypeError):
        log.warning(f"Entity {entity_id} has non-numeric state: {state_obj}")
        return None


def calculate_weighted_climate(
    device_class: SensorDeviceClass,
    weighted_devices: list[tuple[DeviceEntry, float]],
) -> float | None:
    """Calculate weighted average for climate sensors of specified device_class.

    Only uses external weighted sensors (not TRV temperatures).
    Returns weighted average value or None if no valid readings.
    """
    total_weighted_value = 0.0
    total_weight = 0.0

    for device, weight in weighted_devices:
        entity_id = get_climate_entity_for_device(device, device_class)
        if entity_id is None:
            log.debug(f"Device {device.name_by_user} has no {device_class} entity")
            continue

        value = get_sensor_value(entity_id)
        if value is not None:
            log.debug(f"Weighted device {device.name_by_user} {device_class}: {value} (weight {weight})")
            total_weighted_value += value * weight
            total_weight += weight

    if total_weight == 0:
        return None

    return total_weighted_value / total_weight


@service
@time_trigger("startup")
@time_trigger("cron(*/5 * * * *)")
async def update_room_climate_sensors():
    """Publish weighted virtual room climate sensors from external weighted sensors.

    Runs at startup and every 5 min. TRV temperatures are excluded so heating
    doesn't skew the average. If an area has no usable external sensors the virtual
    sensor is set to unavailable (Better Thermostat then handles the missing input).
    """
    log.info("Updating room climate sensors")

    ar = area_registry.async_get(hass)
    trv_devices_by_area, weighted_devices_by_area = get_all_climate_devices()

    log.info(f"Found {len(trv_devices_by_area)} areas with TRVs")

    for area_id, trv_devices in trv_devices_by_area.items():
        area = ar.async_get_area(area_id)
        area_name = area.name if area else area_id
        weighted_devices = weighted_devices_by_area.get(area_id, [])

        # Calculate weighted temperature from external sensors only
        temperature = calculate_weighted_climate(SensorDeviceClass.TEMPERATURE, weighted_devices)
        if temperature is not None:
            state.set(
                f"sensor.climate_{area_id}_temperature",
                value=f"{temperature:.1f}",
                new_attributes={
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                    "state_class": "measurement",
                    "friendly_name": f"{area_name} Temperature",
                },
            )
            log.info(f"Area {area_name}: set virtual temperature sensor to {temperature:.1f}°C")
        else:
            # No external sensors - mark unavailable so Better Thermostat sees no input
            state.set(
                f"sensor.climate_{area_id}_temperature",
                value="unavailable",
                new_attributes={
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                    "state_class": "measurement",
                    "friendly_name": f"{area_name} Temperature",
                },
            )
            log.info(f"Area {area_name}: no external sensors")

        # Calculate weighted humidity from external sensors only
        humidity = calculate_weighted_climate(SensorDeviceClass.HUMIDITY, weighted_devices)
        if humidity is not None:
            state.set(
                f"sensor.climate_{area_id}_humidity",
                value=f"{humidity:.1f}",
                new_attributes={
                    "unit_of_measurement": "%",
                    "device_class": "humidity",
                    "state_class": "measurement",
                    "friendly_name": f"{area_name} Humidity",
                },
            )
            log.info(f"Area {area_name}: set virtual humidity sensor to {humidity:.1f}%")
        else:
            log.debug(f"Area {area_name}: no external humidity sensors")

    log.info("Done updating room climate sensors")
