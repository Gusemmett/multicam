"""Device status manager - polls device status in background"""

import asyncio
import logging
from typing import Dict, Optional

from PySide6.QtCore import QObject, Signal as pyqtSignal

from multicam_common import CommandMessage, StatusResponse, DeviceStatus
from models.app_state import AppState
from services.device_communication import DeviceCommunication

logger = logging.getLogger(__name__)


class DeviceStatusManager(QObject):
    """
    Background service that periodically polls DEVICE_STATUS from all devices.

    Emits signals when device status changes.
    """

    # Signals
    device_status_updated = pyqtSignal(str, object)  # device_name, StatusResponse

    def __init__(
        self,
        app_state: AppState,
        device_comm: DeviceCommunication,
        poll_interval: float = 3.0,
        parent=None
    ):
        """
        Initialize device status manager.

        Args:
            app_state: Application state
            device_comm: Device communication service
            poll_interval: Seconds between status polls (default: 3.0)
        """
        super().__init__(parent)
        self.app_state = app_state
        self.device_comm = device_comm
        self.poll_interval = poll_interval

        self.is_polling = False
        self._poll_task: Optional[asyncio.Task] = None
        self._status_cache: Dict[str, StatusResponse] = {}

    def start_polling(self):
        """Start periodic status polling"""
        if self.is_polling:
            logger.warning("Status polling already running")
            return

        logger.info(f"Starting device status polling (interval: {self.poll_interval}s)")
        self.is_polling = True

        # Schedule the task to start when event loop is available
        try:
            loop = asyncio.get_running_loop()
            self._poll_task = loop.create_task(self._poll_loop())
        except RuntimeError:
            # No running loop yet, schedule for later
            asyncio.ensure_future(self._poll_loop())

    def stop_polling(self):
        """Stop status polling"""
        if not self.is_polling:
            return

        logger.info("Stopping device status polling")
        self.is_polling = False

        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None

    def get_latest_status(self, device_name: str) -> Optional[StatusResponse]:
        """
        Get cached status for a device.

        Args:
            device_name: Device name

        Returns:
            Latest StatusResponse or None if not available
        """
        return self._status_cache.get(device_name)

    def are_all_devices_ready(self) -> bool:
        """
        Check if all discovered devices are reporting 'ready' status.

        Returns:
            True if all devices have status 'ready', False otherwise
        """
        if not self.app_state.discovered_devices:
            return False

        for device in self.app_state.discovered_devices:
            status = self._status_cache.get(device.name)
            if status is None:
                return False
            if status.status.lower() != DeviceStatus.READY.value:
                return False

        return True

    async def _poll_loop(self):
        """Main polling loop"""
        try:
            while self.is_polling:
                await self._poll_all_devices()
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            logger.info("Status polling loop cancelled")
        except Exception as e:
            logger.error(f"Error in status polling loop: {e}")
            self.is_polling = False

    async def _poll_all_devices(self):
        """Poll DEVICE_STATUS from all discovered devices"""
        if not self.app_state.discovered_devices:
            return

        # Create tasks for all devices
        tasks = []
        for device in self.app_state.discovered_devices:
            task = self._poll_device(device)
            tasks.append(task)

        # Run all polls concurrently
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _poll_device(self, device):
        """Poll status from a single device"""
        try:
            # Send DEVICE_STATUS command
            command = CommandMessage.device_status()
            response = await self.device_comm.send_command(device, command)

            # Cache the response
            self._status_cache[device.name] = response

            # Emit signal
            self.device_status_updated.emit(device.name, response)

        except asyncio.TimeoutError:
            logger.debug(f"Status poll timeout for {device.display_name}")
        except Exception as e:
            logger.debug(f"Failed to poll status from {device.display_name}: {e}")
