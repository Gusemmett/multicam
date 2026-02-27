"""Device discovery via mDNS"""

from PySide6.QtCore import QObject, Signal as pyqtSignal, QTimer
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
from typing import Optional
import socket
import logging

from models.device import MultiCamDevice
from models.app_state import AppState
from utils.constants import SERVICE_TYPE, DISCOVERY_TIMEOUT

logger = logging.getLogger(__name__)


class MultiCamServiceListener(ServiceListener):
    """Listener for mDNS service events"""

    def __init__(self, discovery_service: "DeviceDiscovery"):
        self.discovery = discovery_service

    def add_service(self, zc: Zeroconf, type_: str, name: str):
        """Called when a service is discovered"""
        logger.info(f"Service added: {name}")
        info = zc.get_service_info(type_, name)
        if info:
            self.discovery.service_resolved(name, info)

    def remove_service(self, zc: Zeroconf, type_: str, name: str):
        """Called when a service is removed"""
        logger.info(f"Service removed: {name}")
        self.discovery.service_removed(name)

    def update_service(self, zc: Zeroconf, type_: str, name: str):
        """Called when a service is updated"""
        logger.info(f"Service updated: {name}")


class DeviceDiscovery(QObject):
    """Discovers devices on the local network via mDNS"""

    device_discovered = pyqtSignal(MultiCamDevice)
    device_removed = pyqtSignal(str)
    discovery_error = pyqtSignal(str)

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.zeroconf: Optional[Zeroconf] = None
        self.browser: Optional[ServiceBrowser] = None
        self.timeout_timer = QTimer(self)
        self.timeout_timer.timeout.connect(self.on_discovery_timeout)

    def start_discovery(self):
        """Start discovering devices"""
        try:
            self.app_state.is_discovering = True
            self.app_state.update_status("Discovering devices...")
            self.app_state.clear_devices()

            logger.info(f"Starting mDNS discovery for {SERVICE_TYPE}")

            self.zeroconf = Zeroconf()
            listener = MultiCamServiceListener(self)
            self.browser = ServiceBrowser(self.zeroconf, SERVICE_TYPE, listener)

            # Start timeout timer
            self.timeout_timer.start(DISCOVERY_TIMEOUT * 1000)

        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            self.app_state.update_status(f"Discovery failed: {str(e)}")
            self.app_state.is_discovering = False
            self.discovery_error.emit(str(e))

    def stop_discovery(self):
        """Stop discovering devices"""
        logger.info("Stopping mDNS discovery")
        self.timeout_timer.stop()

        if self.browser:
            self.browser.cancel()
            self.browser = None

        if self.zeroconf:
            self.zeroconf.close()
            self.zeroconf = None

        self.app_state.is_discovering = False

    def service_resolved(self, name: str, info):
        """Called when a service is resolved"""
        try:
            # Extract IP address
            if info.addresses:
                ip = socket.inet_ntoa(info.addresses[0])
            else:
                logger.warning(f"No address for service {name}")
                return

            port = info.port

            device = MultiCamDevice(name=name, ip=ip, port=port, service_type=SERVICE_TYPE)

            logger.info(f"Found device: {device.display_name} at {ip}:{port}")
            self.app_state.add_device(device)
            self.device_discovered.emit(device)

        except Exception as e:
            logger.error(f"Failed to process service {name}: {e}")

    def service_removed(self, name: str):
        """Called when a service is removed"""
        logger.info(f"Device removed: {name}")
        self.app_state.remove_device(name)
        self.device_removed.emit(name)

    def on_discovery_timeout(self):
        """Handle discovery timeout"""
        self.timeout_timer.stop()

        device_count = len(self.app_state.discovered_devices)
        if device_count > 0:
            self.app_state.update_status(f"Found {device_count} device(s)")
        else:
            logger.warning("Discovery timeout - no devices found")
            self.app_state.update_status(
                "Auto-discovery timed out. Try manual device connection."
            )

        self.stop_discovery()

    def add_manual_device(self, ip: str, port: int, name: Optional[str] = None):
        """Manually add a device by IP and port"""
        if name is None:
            name = f"manual-{ip}"

        device = MultiCamDevice(name=name, ip=ip, port=port, service_type="_manual._tcp.")

        logger.info(f"Manually added device: {device.display_name} at {ip}:{port}")
        self.app_state.add_device(device)
        self.device_discovered.emit(device)
