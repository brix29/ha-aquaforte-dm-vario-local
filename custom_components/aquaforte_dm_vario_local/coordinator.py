"""AquaForte DataUpdateCoordinator – manages device connection and state."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CTRL_CACHE_SIZE,
    DOMAIN,
    KEEPALIVE_INTERVAL,
    POLL_INTERVAL,
    POST_COMMAND_REFRESH_DELAY,
    RECONNECT_INTERVAL,
    RECONNECT_MAX_INTERVAL,
    WRITABLE_FLAG_SIZE,
    EndpointDef,
)
from .protocol import AquaForteProtocol, build_control_payload, parse_status_buffer

_LOGGER = logging.getLogger(__name__)


class AquaForteCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for one AquaForte device."""

    def __init__(self, hass: HomeAssistant, host: str, device_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{device_id}",
            update_interval=timedelta(seconds=POLL_INTERVAL),
        )
        self.host = host
        self.device_id = device_id
        self._protocol = AquaForteProtocol(host)
        self._keepalive_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._ctrl_bytes: bytes = bytes(CTRL_CACHE_SIZE)
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name="AquaForte DM-VARIO",
            manufacturer="AquaForte",
            model="DM-VARIO WIFI",
            configuration_url=f"http://{host}",
        )

    async def async_setup(self) -> None:
        """Connect to device and start keepalive loop."""
        await self._connect()
        self._keepalive_task = self.hass.async_create_background_task(
            self._keepalive_loop(), f"aquaforte_keepalive_{self.device_id}"
        )

    async def async_shutdown(self) -> None:
        """Disconnect and stop keepalive loop."""
        if self._keepalive_task:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
        await self._protocol.disconnect()

    async def _connect(self) -> None:
        """Establish TCP connection, get passcode, and login."""
        await self._protocol.connect()
        passcode = await self._protocol.get_passcode()
        success = await self._protocol.login(passcode)
        if not success:
            await self._protocol.disconnect()
            raise UpdateFailed("Login to AquaForte device failed")
        _LOGGER.info("Connected and logged in to AquaForte %s (%s)", self.device_id, self.host)

    async def _keepalive_loop(self) -> None:
        """Send ping every KEEPALIVE_INTERVAL seconds; reconnect on failure.

        Reconnect attempts back off exponentially (RECONNECT_INTERVAL up to
        RECONNECT_MAX_INTERVAL) so an unplugged or unreachable pump does not
        flood the network and the log every few seconds. The backoff sleep
        happens OUTSIDE the lock — commands and polls must not queue behind a
        multi-minute wait.
        """
        consecutive_failures = 0
        reconnect_backoff = RECONNECT_INTERVAL
        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL)
            async with self._lock:
                try:
                    await self._protocol.ping()
                    consecutive_failures = 0
                    reconnect_backoff = RECONNECT_INTERVAL
                except Exception as exc:
                    consecutive_failures += 1
                    _LOGGER.warning(
                        "Ping failed (%d/3) for %s: %s", consecutive_failures, self.device_id, exc
                    )

            if consecutive_failures >= 3:
                _LOGGER.error(
                    "Lost connection to %s, reconnecting in %d s…",
                    self.device_id, reconnect_backoff,
                )
                async with self._lock:
                    await self._protocol.disconnect()
                await asyncio.sleep(reconnect_backoff)
                async with self._lock:
                    try:
                        await self._connect()
                        consecutive_failures = 0
                        reconnect_backoff = RECONNECT_INTERVAL
                    except Exception as reconnect_exc:
                        reconnect_backoff = min(reconnect_backoff * 2, RECONNECT_MAX_INTERVAL)
                        _LOGGER.error(
                            "Reconnect failed (next attempt in %d s): %s",
                            reconnect_backoff, reconnect_exc,
                        )
                if consecutive_failures == 0:
                    _LOGGER.info("Reconnected to %s", self.device_id)
                    await self.async_request_refresh()
                continue

            # Outside the lock: the device relays control commands sent by
            # OTHER LAN clients (official app, a second HA) to us. Turn such
            # an echo into a prompt refresh so entities follow external
            # changes within seconds instead of the next scheduled poll.
            if self._protocol.consume_control_activity():
                _LOGGER.debug(
                    "Control command from another client seen on %s, refreshing",
                    self.device_id,
                )
                await self._delayed_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll device status."""
        async with self._lock:
            try:
                raw = await self._protocol.read_status()
            except Exception as exc:
                raise UpdateFailed(f"Failed to read status from {self.device_id}: {exc}") from exc

        if len(raw) >= CTRL_CACHE_SIZE:
            self._ctrl_bytes = raw[:CTRL_CACHE_SIZE]

        return parse_status_buffer(raw)

    async def set_value(self, endpoint: EndpointDef, value: Any) -> None:
        """Send a command and refresh state."""
        async with self._lock:
            try:
                await self._protocol.send_command(endpoint, value, self._ctrl_bytes)
            except Exception as exc:
                raise UpdateFailed(f"Command failed for {endpoint.name}: {exc}") from exc

        new_payload = build_control_payload(endpoint, value, self._ctrl_bytes)
        if len(new_payload) >= WRITABLE_FLAG_SIZE + CTRL_CACHE_SIZE:
            self._ctrl_bytes = new_payload[WRITABLE_FLAG_SIZE: WRITABLE_FLAG_SIZE + CTRL_CACHE_SIZE]

        # Commands are fire-and-forget and the pump applies them
        # asynchronously — a refresh issued immediately still reads the OLD
        # state, which then sticks until the next scheduled poll. A short
        # delay before the verify poll lets the pump apply the command first.
        self.hass.async_create_task(self._delayed_refresh())

    async def _delayed_refresh(self) -> None:
        """Poll the device state shortly after a control command."""
        await asyncio.sleep(POST_COMMAND_REFRESH_DELAY)
        await self.async_request_refresh()
