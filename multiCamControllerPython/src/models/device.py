"""MultiCam device model"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class DeviceType(Enum):
    """Type of camera device"""

    IPHONE = "iphone"
    OAK = "oak"
    MANUAL = "manual"


@dataclass
class MultiCamDevice:
    """Represents a discovered or manually added camera device"""

    name: str
    ip: str
    port: int
    service_type: str = "_multicam._tcp.local."
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_connected: bool = False
    last_seen: datetime = field(default_factory=datetime.now)

    @property
    def display_name(self) -> str:
        """Extract clean device name"""
        clean_name = self.name.replace("._multicam._tcp.local.", "")
        if clean_name.startswith("multiCam-"):
            clean_name = clean_name[9:]  # Remove 'multiCam-' prefix
        return clean_name

    @property
    def device_type(self) -> DeviceType:
        """Determine device type from name"""
        if "manual-" in self.name:
            return DeviceType.MANUAL
        elif "oak" in self.display_name.lower():
            return DeviceType.OAK
        else:
            return DeviceType.IPHONE

    @property
    def device_icon(self) -> str:
        """Return text icon for device type"""
        icons = {
            DeviceType.IPHONE: "[iPhone]",
            DeviceType.OAK: "[OAK]",
            DeviceType.MANUAL: "[Manual]",
        }
        return icons[self.device_type]

    def __hash__(self):
        """Make device hashable for use in sets/dicts"""
        return hash(self.id)

    def __eq__(self, other):
        """Compare devices by ID"""
        if not isinstance(other, MultiCamDevice):
            return False
        return self.id == other.id
