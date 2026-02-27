"""Application state management"""

import logging
from PySide6.QtCore import QObject, Signal as pyqtSignal
from typing import List
from .device import MultiCamDevice
from .recording_session import RecordingSession
from .app_settings import AppSettings

logger = logging.getLogger(__name__)


class AppState(QObject):
    """Central application state"""

    devices_changed = pyqtSignal()
    status_changed = pyqtSignal(str)
    discovery_state_changed = pyqtSignal(bool)
    settings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.discovered_devices: List[MultiCamDevice] = []
        self.status_message = "Ready"
        self.is_discovering = False
        self.recording_session = RecordingSession(self)

        # Application settings
        self.settings = AppSettings.load()

        # S3 Configuration (bucket comes from settings, region is constant)
        self.s3_bucket_name = self.settings.s3_bucket
        self.s3_region = "us-east-1"

    def update_status(self, message: str):
        """Update status message"""
        self.status_message = message
        self.status_changed.emit(message)

    def add_device(self, device: MultiCamDevice):
        """Add or update a device"""
        # Update existing device or add new one
        for i, existing in enumerate(self.discovered_devices):
            if existing.name == device.name:
                self.discovered_devices[i] = device
                self.devices_changed.emit()
                return

        self.discovered_devices.append(device)
        self.devices_changed.emit()

    def remove_device(self, device_name: str):
        """Remove a device by name"""
        self.discovered_devices = [d for d in self.discovered_devices if d.name != device_name]
        self.devices_changed.emit()

    def clear_devices(self):
        """Clear all devices"""
        self.discovered_devices.clear()
        self.devices_changed.emit()

    def update_settings(self, new_settings: AppSettings):
        """Update application settings and emit signal"""
        old_bucket = self.settings.s3_bucket
        self.settings = new_settings

        # Update bucket if it changed
        if old_bucket != new_settings.s3_bucket:
            self.s3_bucket_name = new_settings.s3_bucket
            logger.info(f"S3 bucket changed to: {self.s3_bucket_name}")

        self.settings_changed.emit()

    @property
    def device_status_text(self) -> str:
        """Get formatted device status text"""
        if not self.discovered_devices:
            return """No devices discovered yet.

Make sure:
• iPhone multiCam apps are running
• OAK cameras are running and on network
• All devices on same WiFi network
"""

        device_list = "\n".join(
            [
                f"{d.device_icon} {d.display_name}: {d.ip}:{d.port}"
                for d in self.discovered_devices
            ]
        )
        return device_list
