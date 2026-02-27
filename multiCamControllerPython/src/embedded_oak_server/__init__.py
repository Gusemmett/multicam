"""
Embedded OAK Server package.

This package embeds the OAK-Controller-Rpi device server functionality,
allowing the controller to act as both a client and server for OAK cameras.
"""

from .oak_device import MultiCamDevice
from .tcp_server import MultiCamServer
from .camera_detector import detect_oak_cameras, is_oak_camera_connected, get_primary_oak_device

__all__ = [
    "MultiCamDevice",
    "MultiCamServer",
    "detect_oak_cameras",
    "is_oak_camera_connected",
    "get_primary_oak_device",
]
