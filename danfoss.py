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
CLUSTER_ID_THERMOSTAT = 0x0201
ATTR_RADIATOR_COVERED = 0x4016
CLUSTER_TYPE = "in"
LABEL_RADIATOR_COVERED = "radiator_covered"


hass: HomeAssistant
log: Logger


@service
async def danfoss():

    zha_gateway = get_zha_gateway(hass)
    dr = device_registry.async_get(hass)

    log.info("Checking radiator covered attributes")

    for device_id in dr.devices:
        device: DeviceEntry | None = dr.async_get(device_id)

        if device is None or device.model != DEVICE_MODEL:
            continue

        log.info(f"Checking radiator covered attribute: {device.name_by_user} ({device.id})")

        ieee: EUI64 | None = None
        for domain, identifier in device.identifiers:
            if domain != ZHA_DOMAIN:
                continue
            ieee = EUI64.convert(identifier)

        if ieee is None:
            log.error(f"No IEEE address found for device {device.name_by_user} ({device.id})")
            continue

        zha_device: Device | None = zha_gateway.get_device(ieee)
        if zha_device is None:
            log.error(f"Device {device.name_by_user} ({device.id}) not found in ZHA network")
            continue

        cluster = zha_device.async_get_cluster(
            ENDPOINT_ID, CLUSTER_ID_THERMOSTAT, cluster_type=CLUSTER_TYPE
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
            ENDPOINT_ID, CLUSTER_ID_THERMOSTAT, ATTR_RADIATOR_COVERED, should_be_true, cluster_type=CLUSTER_TYPE, manufacturer=zha_device.manufacturer_code,
        )

        if response is None:
            log.error(f"Failed to write radiator covered attribute for device {device.name_by_user} ({device.id})")
            continue

        log.info(f"Successfully set radiator covered attribute {should_be_true} for device {device.name_by_user} ({device.id})")

    log.info("Done checking radiator covered attributes")
