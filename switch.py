"""AquaForte switch entities."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import EP_FEED_SWITCH, EP_SWITCH_ON, EndpointDef
from .coordinator import AquaForteCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AquaForteCoordinator = entry.runtime_data

    async_add_entities(
        [
            AquaForteSwitch(coordinator, EP_SWITCH_ON, "power", "mdi:pump"),
            AquaForteSwitch(coordinator, EP_FEED_SWITCH, "feed_mode", "mdi:fish"),
        ]
    )


class AquaForteSwitch(CoordinatorEntity[AquaForteCoordinator], SwitchEntity):
    """AquaForte switch entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AquaForteCoordinator,
        endpoint: EndpointDef,
        translation_key: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self._endpoint = endpoint
        self._attr_translation_key = translation_key
        self._attr_icon = icon
        self._attr_unique_id = f"{coordinator.device_id}_{endpoint.name}"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None

        return self.coordinator.data.get(self._endpoint.name)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.set_value(self._endpoint, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.set_value(self._endpoint, False)