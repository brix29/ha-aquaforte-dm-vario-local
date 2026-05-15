"""AquaForte DM-VARIO WIFI Home Assistant integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_DEVICE_ID, CONF_HOST, DOMAIN
from .coordinator import AquaForteCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch", "number", "select", "binary_sensor"]

type AquaForteConfigEntry = ConfigEntry[AquaForteCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AquaForteConfigEntry) -> bool:
    """Set up AquaForte from a config entry."""
    host = entry.data[CONF_HOST]
    device_id = entry.data.get(CONF_DEVICE_ID, host)

    coordinator = AquaForteCoordinator(hass, host, device_id)

    try:
        await coordinator.async_setup()
        await coordinator.async_config_entry_first_refresh()
    except Exception as exc:
        raise ConfigEntryNotReady(f"Cannot connect to AquaForte at {host}: {exc}") from exc

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AquaForteConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: AquaForteCoordinator = entry.runtime_data
        await coordinator.async_shutdown()
    return unloaded
