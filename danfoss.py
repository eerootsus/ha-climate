import datetime
from logging import Logger
from homeassistant.core import HomeAssistant
from homeassistant.components.zha.const import DOMAIN as ZHA_DOMAIN
from homeassistant.components.zha.helpers import get_zha_gateway
from homeassistant.helpers import device_registry
from homeassistant.helpers.device_registry import DeviceEntry
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


LABEL_RADIATOR_COVERED = "radiator_covered"


hass: HomeAssistant
log: Logger


def get_devices() -> list[DeviceEntry]:
    dr = device_registry.async_get(hass)
    devices = []
    for device_id in dr.devices:
        device: DeviceEntry | None = dr.async_get(device_id)
        if device is None or device.model != DEVICE_MODEL:
            continue
        devices.append(device)
    return devices


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


@service
@time_trigger("startup")
async def set_time():
    log.info("Setting current time on devices")
    epoch = datetime.datetime(2000, 1, 1, 0, 0, 0, 0, datetime.UTC)
    for device in get_devices():
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
async def radiator_covered():
    log.info("Checking radiator covered attributes")

    for device in get_devices():
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
