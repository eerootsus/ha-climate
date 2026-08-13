"""Temporary diagnostic: read raw Zigbee attributes off each Danfoss eTRV and
publish them as attributes on sensor.trv_debug_<name>, so they can be inspected
via the REST API. Read-only — performs no writes.

Deploy: copy to config/pyscript/, reload pyscript, then call the service
pyscript.dump_trv_attributes. Remove when done.
"""

from logging import Logger
from homeassistant.core import HomeAssistant
from homeassistant.components.zha.const import DOMAIN as ZHA_DOMAIN
from homeassistant.components.zha.helpers import get_zha_gateway
from homeassistant.helpers import device_registry
from homeassistant.helpers.device_registry import DeviceEntry
from zigpy.types.named import EUI64
from zha.exceptions import ZHAException

DEVICE_MODEL = "eTRV0103"
ENDPOINT_ID = 1
CLUSTER_TYPE = "in"

THERMOSTAT = 0x0201
UI = 0x0204
DIAGNOSTICS = 0x0b05

# (cluster, attribute, manufacturer_specific, label)
READS = [
    (THERMOSTAT, 0x0008, False, "pi_heating_demand"),
    (THERMOSTAT, 0x0010, False, "local_temp_calibration"),
    (THERMOSTAT, 0x0012, False, "occupied_setpoint"),
    (THERMOSTAT, 0x001C, False, "system_mode"),
    (THERMOSTAT, 0x0025, False, "programming_oper_mode"),
    (THERMOSTAT, 0x4015, True, "external_measured_sensor"),
    (THERMOSTAT, 0x4016, True, "radiator_covered"),
    (THERMOSTAT, 0x4030, True, "heat_available"),
    (THERMOSTAT, 0x4031, True, "heat_required"),
    (THERMOSTAT, 0x4032, True, "load_balancing_enable"),
    (THERMOSTAT, 0x404B, True, "regulation_setpoint_offset"),
    (THERMOSTAT, 0x404D, True, "adaptation_run_status"),
    (UI,         0x4020, True, "heating_control_scale"),
    (DIAGNOSTICS, 0x4000, True, "sw_error_code"),
]

hass: HomeAssistant
log: Logger


def _get_trvs() -> list[DeviceEntry]:
    dr = device_registry.async_get(hass)
    out = []
    for device_id in dr.devices:
        dev = dr.async_get(device_id)
        if dev is not None and dev.model == DEVICE_MODEL:
            out.append(dev)
    return out


def _zha_device(device: DeviceEntry):
    gw = get_zha_gateway(hass)
    for domain, ident in device.identifiers:
        if domain == ZHA_DOMAIN:
            return gw.get_device(EUI64.convert(ident))
    return None


@service
async def dump_trv_attributes():
    """Read raw Zigbee attributes from every Danfoss eTRV and publish them as
    attributes on sensor.trv_debug_<name>."""
    log.info("Dumping TRV attributes")

    for device in _get_trvs():
        zha = _zha_device(device)
        name = (device.name_by_user or device.name or device.id).lower()
        safe = ""
        for ch in name:
            safe += ch if ch.isalnum() else "_"
        if zha is None:
            log.warning(f"No ZHA device for {name}")
            continue

        mfg = zha.manufacturer_code
        results = {}
        for cluster_id, attr, mfg_specific, key in READS:
            try:
                cluster = zha.async_get_cluster(ENDPOINT_ID, cluster_id, cluster_type=CLUSTER_TYPE)
                ok, fail = await cluster.read_attributes(
                    [attr],
                    allow_cache=True,
                    only_cache=False,
                    manufacturer=(mfg if mfg_specific else None),
                )
                if attr in ok:
                    results[key] = str(ok[attr])
                else:
                    results[key] = "FAIL"
            except (TimeoutError, ZHAException) as e:
                results[key] = f"ERR:{type(e).__name__}"
            except Exception as e:
                results[key] = f"ERR:{type(e).__name__}:{e}"

        state.set(f"sensor.trv_debug_{safe}", value="ok", new_attributes=results)
        log.info(f"{name}: {results}")

    log.info("Done dumping TRV attributes")
