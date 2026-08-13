"""Temporary: unstick a Danfoss eTRV's PID that's holding a low non-zero demand.

Community-reported fix (z2m #19495): cycle radiator_covered (0x4016) and nudge the
setpoint to force the PID to recompute. Each write retries through the eTRV's wake
windows (inline, not via the dedup retry queue, so the True->False cycle survives).

Deploy: copy to config/pyscript/, reload pyscript, then call:
  pyscript.unstick_trvs            -> all TRVs
  pyscript.unstick_trvs only=ada   -> just the TRV whose name contains 'ada'
Remove when done.
"""

from logging import Logger
from homeassistant.core import HomeAssistant
from homeassistant.components.zha.const import DOMAIN as ZHA_DOMAIN
from homeassistant.components.zha.helpers import get_zha_gateway
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.device_registry import DeviceEntry
from zigpy.types.named import EUI64
from zha.exceptions import ZHAException

DEVICE_MODEL = "eTRV0103"
ENDPOINT_ID = 1
CLUSTER_TYPE = "in"
THERMOSTAT = 0x0201
ATTR_RADIATOR_COVERED = 0x4016
ATTR_OCCUPIED_SETPOINT = 0x0012
MFG_MIN = 0x4000

WRITE_RETRIES = 6
RETRY_SLEEP = 18   # seconds between attempts (eTRV wakes ~every 5 min, so retry often)
STEP_SLEEP = 5     # settle time between sequence steps

hass: HomeAssistant
log: Logger


def _trvs() -> list[DeviceEntry]:
    dr = device_registry.async_get(hass)
    out = []
    for did in dr.devices:
        dev = dr.async_get(did)
        if dev is not None and dev.model == DEVICE_MODEL:
            out.append(dev)
    return out


def _zha(device: DeviceEntry):
    gw = get_zha_gateway(hass)
    for dom, ident in device.identifiers:
        if dom == ZHA_DOMAIN:
            return gw.get_device(EUI64.convert(ident))
    return None


def _setpoint_of(device: DeviceEntry):
    er = entity_registry.async_get(hass)
    for entry in er.entities.get_entries_for_device_id(device.id):
        if entry.domain == "climate":
            try:
                sp = state.getattr(entry.entity_id).get("occupied_heating_setpoint")
                return int(sp) if sp is not None else None
            except Exception:
                return None
    return None


async def _write(zha, attr, value, label):
    mfg = zha.manufacturer_code if attr >= MFG_MIN else None
    cluster = zha.async_get_cluster(ENDPOINT_ID, THERMOSTAT, cluster_type=CLUSTER_TYPE)
    for i in range(WRITE_RETRIES):
        try:
            resp = await cluster.write_attributes({attr: value}, manufacturer=mfg)
            if resp is not None:
                log.info(f"{label}: wrote 0x{attr:04x}={value} OK (try {i + 1})")
                return True
            log.warning(f"{label}: 0x{attr:04x}={value} returned None (try {i + 1})")
        except (TimeoutError, ZHAException) as e:
            log.warning(f"{label}: 0x{attr:04x}={value} try {i + 1} failed: {e}")
        except Exception as e:
            log.warning(f"{label}: 0x{attr:04x}={value} try {i + 1} error: {e}")
        await task.sleep(RETRY_SLEEP)
    log.error(f"{label}: GAVE UP on 0x{attr:04x}={value} after {WRITE_RETRIES} tries")
    return False


@service
async def unstick_trvs(only=None):
    """Cycle radiator_covered + nudge setpoint to force the PID to recompute.

    only: optional name substring to target a single TRV (e.g. only='ada').
    """
    for device in _trvs():
        name = (device.name_by_user or device.name or "").lower()
        if only and only.lower() not in name:
            continue
        zha = _zha(device)
        if zha is None:
            log.warning(f"{name}: no ZHA device, skipping")
            continue

        sp = _setpoint_of(device)
        log.info(f"=== unsticking {name} (current setpoint={sp}) ===")

        # 1) cycle radiator_covered: True, then back to False (exposed)
        await _write(zha, ATTR_RADIATOR_COVERED, True, name)
        await task.sleep(STEP_SLEEP)
        await _write(zha, ATTR_RADIATOR_COVERED, False, name)
        await task.sleep(STEP_SLEEP)

        # 2) nudge the setpoint up 1C then restore (forces PID recompute, keeps user value)
        if sp is not None:
            await _write(zha, ATTR_OCCUPIED_SETPOINT, sp + 100, name)
            await task.sleep(STEP_SLEEP)
            await _write(zha, ATTR_OCCUPIED_SETPOINT, sp, name)
        else:
            log.warning(f"{name}: no setpoint read, skipping nudge")

        log.info(f"=== done {name} ===")

    log.info("unstick_trvs complete")
