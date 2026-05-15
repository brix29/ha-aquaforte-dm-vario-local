"""AquaForte select entity."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import AUTOMODE_OPTIONS, EP_AUTO_MODE
from .coordinator import AquaForteCoordinator

OPTION_TO_STATE = {
    "Shutdown": "shutdown",
    "Automatic": "automatic",
    "Feed": "feed",
}

STATE_TO_OPTION = {state: option for option, state in OPTION_TO_STATE.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AquaForteCoordinator = entry.runtime_data
    async_add_entities([AquaForteModeSelect(coordinator)])


class AquaForteModeSelect(CoordinatorEntity[AquaForteCoordinator], SelectEntity):
    """AquaForte operating mode select entity."""

    _attr_has_entity_name = True
    _attr_translation_key = "operating_mode"
    _attr_icon = "mdi:cog"
    _attr_options = [OPTION_TO_STATE[option] for option in AUTOMODE_OPTIONS]

    def __init__(self, coordinator: AquaForteCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_{EP_AUTO_MODE.name}"
        self._attr_device_info = coordinator.device_info

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None

        raw = self.coordinator.data.get(EP_AUTO_MODE.name)
        return OPTION_TO_STATE.get(raw)

    async def async_select_option(self, option: str) -> None:
        value = STATE_TO_OPTION.get(option, "Shutdown")
        await self.coordinator.set_value(EP_AUTO_MODE, value)