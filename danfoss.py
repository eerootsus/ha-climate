import datetime
from logging import Logger
from homeassistant.core import HomeAssistant
from homeassistant.components.zha.const import DOMAIN as ZHA_DOMAIN
from homeassistant.components.zha.helpers import get_zha_gateway
from homeassistant.helpers import area_registry, device_registry, entity_registry
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.components.sensor import SensorDeviceClass
from zigpy.types.named import EUI64
from zha.zigbee.device import Device

DEVICE_MODEL = "eTRV0103"
ENDPOINT_ID = 1
CLUSTER_TYPE = "in"

CLUSTER_TIME = 0x000A
CLUSTER_THERMOSTAT = 0x0201
CLUSTER_DIAGNOSTICS = 0x0b05

ATTR_TIME = 0x0000
ATTR_SW_ERROR = 0x4000
ATTR_RADIATOR_COVERED = 0x4016
ATTR_EXTERNAL_MEASURED_ROOM_SENSOR = 0x4015

EXTERNAL_SENSOR_DISABLED = -8000

LABEL_RADIATOR_COVERED = "radiator_covered"
LABEL_SENSOR_WEIGHT_PREFIX = "sensor_weight_"


hass: HomeAssistant
log: Logger


def get_trv_devices() -> list[DeviceEntry]:
    """Get all TRV devices."""
    dr = device_registry.async_get(hass)
    devices = []
    for device_id in dr.devices:
        device: DeviceEntry | None = dr.async_get(device_id)
        if device is None or device.model != DEVICE_MODEL:
            continue
        devices.append(device)
    return devices


def get_all_climate_devices() -> tuple[dict[str, list[DeviceEntry]], dict[str, list[tuple[DeviceEntry, float]]]]:
    """Scan all devices once and return TRVs and weighted devices grouped by area.

    Returns (trv_devices_by_area, weighted_devices_by_area).
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


def get_zigbee_device(device: DeviceEntry) -> Device | None:
    zha_gateway = get_zha_gateway(hass)
    ieee: EUI64 | None = None
    for domain, identifier in device.identifiers:
        if domain != ZHA_DOMAIN:
            continue
        ieee = EUI64.convert(identifier)

    if ieee is None:
        log.error(f"No IEEE address found for device {device.name_by_user} ({device.id})")
        return None

    return zha_gateway.get_device(ieee)


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
    trv_devices: list[DeviceEntry],
    weighted_devices: list[tuple[DeviceEntry, float]],
) -> float | None:
    """Calculate weighted average for climate sensors of specified device_class.

    Includes TRV sensors (weight 0.5) and any additional weighted devices.
    Returns weighted average value or None if no valid readings.
    """
    total_weighted_value = 0.0
    total_weight = 0.0

    # Include TRV sensors with weight 0.5
    for device in trv_devices:
        entity_id = get_climate_entity_for_device(device, device_class)
        if entity_id is None:
            continue

        value = get_sensor_value(entity_id)
        if value is not None:
            log.debug(f"TRV {device.name_by_user} {device_class}: {value} (weight 0.5)")
            total_weighted_value += value * 0.5
            total_weight += 0.5

    # Include weighted devices
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
@time_trigger("cron(0 3 * * 0)")
async def set_time():
    """Set current time on TRV devices. Runs at startup and weekly (Sunday 3:00 AM)."""
    log.info("Setting current time on devices")
    epoch = datetime.datetime(2000, 1, 1, 0, 0, 0, 0, datetime.UTC)
    for device in get_trv_devices():
        log.info(f"Setting time on device: {device.name_by_user} ({device.id})")
        zha_device = get_zigbee_device(device)
        if zha_device is None:
            log.error(f"Device {device.name_by_user} ({device.id}) not found in ZHA network")
            continue

        cluster = zha_device.async_get_cluster(
            ENDPOINT_ID, CLUSTER_TIME, cluster_type=CLUSTER_TYPE
        )

        time = (datetime.datetime.now(datetime.UTC) - epoch).total_seconds()

        response = zha_device.write_zigbee_attribute(
            ENDPOINT_ID, CLUSTER_TIME, ATTR_TIME, time, cluster_type=CLUSTER_TYPE, manufacturer=zha_device.manufacturer_code,
        )

        if response is None:
            log.error(f"Failed to update time for device {device.name_by_user} ({device.id})")
            continue

        log.info(f"Successfully set time on device {device.name_by_user} ({device.id})")


@service
@time_trigger("startup")
@time_trigger("cron(0 3 * * 0)")
async def radiator_covered():
    """Check and set radiator covered attributes. Runs at startup and weekly (Sunday 3:00 AM)."""
    log.info("Checking radiator covered attributes")

    for device in get_trv_devices():
        log.info(f"Checking radiator covered attribute: {device.name_by_user} ({device.id})")
        zha_device = get_zigbee_device(device)
        if zha_device is None:
            log.error(f"Device {device.name_by_user} ({device.id}) not found in ZHA network")
            continue

        cluster = zha_device.async_get_cluster(
            ENDPOINT_ID, CLUSTER_THERMOSTAT, cluster_type=CLUSTER_TYPE
        )
        success, failure = cluster.read_attributes(
            [ATTR_RADIATOR_COVERED], allow_cache=False, only_cache=False, manufacturer=zha_device.manufacturer_code
        )

        if failure:
            log.error(f"Failed to read radiator covered attribute for device {device.name_by_user} ({device.id})")
            continue

        should_be_true = LABEL_RADIATOR_COVERED in device.labels

        if success.get(ATTR_RADIATOR_COVERED) == should_be_true:
            log.info(f"Radiator covered attribute is correct ({should_be_true}) for device {device.name_by_user} ({device.id})")
            continue

        response = zha_device.write_zigbee_attribute(
            ENDPOINT_ID, CLUSTER_THERMOSTAT, ATTR_RADIATOR_COVERED, should_be_true, cluster_type=CLUSTER_TYPE, manufacturer=zha_device.manufacturer_code,
        )

        if response is None:
            log.error(f"Failed to write radiator covered attribute for device {device.name_by_user} ({device.id})")
            continue

        log.info(f"Successfully set radiator covered attribute {should_be_true} for device {device.name_by_user} ({device.id})")

    log.info("Done checking radiator covered attributes")


@service
@time_trigger("startup")
@time_trigger("cron(*/5 * * * *)")
async def update_room_climate_sensors():
    """Update virtual room climate sensors from TRV and weighted physical sensors."""
    log.info("Updating room climate sensors")

    ar = area_registry.async_get(hass)
    trv_devices_by_area, weighted_devices_by_area = get_all_climate_devices()

    log.info(f"Found {len(trv_devices_by_area)} areas with TRVs")

    for area_id, trv_devices in trv_devices_by_area.items():
        area = ar.async_get_area(area_id)
        area_name = area.name if area else area_id
        weighted_devices = weighted_devices_by_area.get(area_id, [])

        # Calculate weighted temperature (TRVs + weighted devices)
        temperature = calculate_weighted_climate(SensorDeviceClass.TEMPERATURE, trv_devices, weighted_devices)
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
            log.warning(f"Area {area_name}: no valid temperature readings")

        # Calculate weighted humidity (TRVs + weighted devices)
        humidity = calculate_weighted_climate(SensorDeviceClass.HUMIDITY, trv_devices, weighted_devices)
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
            log.debug(f"Area {area_name}: no valid humidity readings")

    log.info("Done updating room climate sensors")

    # Immediately update TRVs with new temperatures
    await update_external_temperatures()


@service
async def update_external_temperatures():
    """Update external temperature on all TRVs from virtual room sensors."""
    log.info("Updating external temperatures on TRVs")

    trv_devices_by_area, _ = get_all_climate_devices()

    for area_id, devices in trv_devices_by_area.items():
        # Read from virtual sensor
        virtual_sensor = f"sensor.climate_{area_id}_temperature"
        try:
            state_obj = state.get(virtual_sensor)
        except NameError:
            log.debug(f"Area {area_id}: virtual sensor does not exist, disabling external sensor")
            temperature = EXTERNAL_SENSOR_DISABLED
        else:
            if state_obj is not None and state_obj not in ("unavailable", "unknown"):
                try:
                    temp_celsius = float(state_obj)
                    temperature = int(round(temp_celsius * 100))  # Convert to centidegrees
                    log.info(f"Area {area_id}: read {temp_celsius:.1f}°C from virtual sensor")
                except (ValueError, TypeError):
                    log.warning(f"Area {area_id}: virtual sensor has invalid state: {state_obj}")
                    temperature = EXTERNAL_SENSOR_DISABLED
            else:
                log.debug(f"Area {area_id}: virtual sensor unavailable, disabling external sensor")
                temperature = EXTERNAL_SENSOR_DISABLED

        for device in devices:
            zha_device = get_zigbee_device(device)
            if zha_device is None:
                log.error(f"Device {device.name_by_user} ({device.id}) not found in ZHA network")
                continue

            response = zha_device.write_zigbee_attribute(
                ENDPOINT_ID,
                CLUSTER_THERMOSTAT,
                ATTR_EXTERNAL_MEASURED_ROOM_SENSOR,
                temperature,
                cluster_type=CLUSTER_TYPE,
                manufacturer=zha_device.manufacturer_code,
            )

            if response is None:
                log.error(f"Failed to write external temperature for device {device.name_by_user} ({device.id})")
                continue

            if temperature == EXTERNAL_SENSOR_DISABLED:
                log.info(f"Disabled external sensor for device {device.name_by_user} ({device.id})")
            else:
                log.info(f"Set external temperature {temperature / 100:.1f}°C on device {device.name_by_user} ({device.id})")

    log.info("Done updating external temperatures")
