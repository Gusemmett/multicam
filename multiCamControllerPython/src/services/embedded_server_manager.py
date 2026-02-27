"""
Embedded OAK Server Manager

Manages the lifecycle of the embedded OAK device server, allowing the controller
to also act as a device server for locally-connected OAK cameras.
"""

import asyncio
import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class EmbeddedServerManager(QObject):
    """
    Manages the embedded OAK server lifecycle.

    The embedded server allows the controller app to also function as an OAK
    device server, registering on mDNS so it appears as a discoverable device.
    """

    # Signals
    server_started = Signal()
    server_stopped = Signal()
    server_error = Signal(str)
    camera_status_changed = Signal(bool)  # True if camera connected

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        self._oak_device = None
        self._tcp_server = None
        self._server_task = None
        self._is_running = False
        self._port = 8080

    @property
    def is_running(self) -> bool:
        """Check if the embedded server is running."""
        return self._is_running

    @property
    def camera_connected(self) -> bool:
        """Check if an OAK camera is currently connected."""
        if self._oak_device:
            return self._oak_device.camera_connected
        return False

    @property
    def device_id(self) -> Optional[str]:
        """Get the device ID of the embedded server."""
        if self._oak_device:
            return self._oak_device.device_id
        return None

    async def start_server(self, port: int = 8080) -> bool:
        """
        Start the embedded OAK server.

        Args:
            port: TCP port for the server (default: 8080)

        Returns:
            True if server started successfully, False otherwise.
        """
        if self._is_running:
            logger.warning("Embedded server already running")
            return True

        self._port = port

        try:
            logger.info(f"Starting embedded OAK server on port {port}...")

            # Import here to avoid loading depthai if not needed
            from embedded_oak_server import MultiCamDevice, MultiCamServer

            # Create the device instance
            self._oak_device = MultiCamDevice(port=port)

            # Create the TCP server
            self._tcp_server = MultiCamServer(self._oak_device)

            # Start mDNS registration
            await self._oak_device.start_mdns()

            # Start TCP server
            server = await self._tcp_server.start()

            # Create a task to keep the server running (use ensure_future for qasync compatibility)
            self._server_task = asyncio.ensure_future(server.serve_forever())

            self._is_running = True
            logger.info(f"Embedded OAK server started successfully on port {port}")
            logger.info(f"Device ID: {self._oak_device.device_id}")
            logger.info(f"Camera connected: {self._oak_device.camera_connected}")

            self.server_started.emit()

            if self._oak_device.camera_connected:
                self.camera_status_changed.emit(True)

            return True

        except ImportError as e:
            error_msg = f"Failed to import embedded server modules. DepthAI may not be installed: {e}"
            logger.error(error_msg)
            self.server_error.emit(error_msg)
            return False

        except Exception as e:
            error_msg = f"Failed to start embedded OAK server: {e}"
            logger.error(error_msg)
            logger.exception("Full exception details:")
            self.server_error.emit(error_msg)
            await self._cleanup()
            return False

    async def stop_server(self) -> None:
        """Stop the embedded OAK server gracefully."""
        if not self._is_running:
            logger.debug("Embedded server not running, nothing to stop")
            return

        logger.info("Stopping embedded OAK server...")

        try:
            await self._cleanup()
            logger.info("Embedded OAK server stopped successfully")
            self.server_stopped.emit()

        except Exception as e:
            logger.error(f"Error stopping embedded server: {e}")
            logger.exception("Full exception details:")
            self.server_error.emit(f"Error stopping server: {e}")

    async def _cleanup(self) -> None:
        """Clean up server resources."""
        # Cancel the server task
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
            self._server_task = None

        # Stop mDNS
        if self._oak_device:
            try:
                await self._oak_device.stop_mdns()
            except Exception as e:
                logger.warning(f"Error stopping mDNS: {e}")
            self._oak_device = None

        self._tcp_server = None
        self._is_running = False

    def get_status(self) -> dict:
        """
        Get the current status of the embedded server.

        Returns:
            Dictionary with server status information.
        """
        return {
            "running": self._is_running,
            "port": self._port if self._is_running else None,
            "device_id": self.device_id,
            "camera_connected": self.camera_connected,
        }
