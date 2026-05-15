"""AquaForte number entities."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import EP_FEED_TIME, EP_MOTOR_SPEED, EndpointDef
from .coordinator import AquaForteCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AquaForteCoordinator = entry.runtime_data

    async_add_entities(
        [
            AquaForteNumber(
                coordinator=coordinator,
                endpoint=EP_MOTOR_SPEED,
                translation_key="pump_speed",
                icon="mdi:speedometer",
                native_min=30,
                native_max=100,
                native_step=1,
                native_unit=PERCENTAGE,
                mode=NumberMode.SLIDER,
            ),
            AquaForteNumber(
                coordinator=coordinator,
                endpoint=EP_FEED_TIME,
                translation_key="feed_duration",
                icon="mdi:timer",
                native_min=1,
                native_max=60,
                native_step=1,
                native_unit=UnitOfTime.SECONDS,
                mode=NumberMode.BOX,
            ),
        ]
    )


class AquaForteNumber(CoordinatorEntity[AquaForteCoordinator], NumberEntity):
    """AquaForte number entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AquaForteCoordinator,
        endpoint: EndpointDef,
        translation_key: str,
        icon: str,
        native_min: int,
        native_max: int,
        native_step: int,
        native_unit: str,
        mode: NumberMode,
    ) -> None:
        super().__init__(coordinator)
        self._endpoint = endpoint
        self._attr_translation_key = translation_key
        self._attr_icon = icon
        self._attr_native_min_value = native_min
        self._attr_native_max_value = native_max
        self._attr_suggested_display_precision = 0        
        self._attr_native_step = native_step
        self._attr_native_unit_of_measurement = native_unit
        self._attr_mode = mode
        self._attr_unique_id = f"{coordinator.device_id}_{endpoint.name}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None

        val = self.coordinator.data.get(self._endpoint.name)
        return float(val) if val is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.set_value(self._endpoint, int(value))