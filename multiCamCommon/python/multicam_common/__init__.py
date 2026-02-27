"""
MultiCam Common API - Python Package

Shared types, enums, and constants for the MultiCam synchronized recording API.
"""

from .commands import (
    CommandType,
    CommandMessage,
    StatusResponse,
    StopRecordingResponse,
    ErrorResponse,
    FileResponse,
    FileMetadata,
    ListFilesResponse,
    UploadStatus,
    UploadItem,
)
from .status import DeviceStatus, DeviceType
from .constants import (
    TCP_PORT,
    SERVICE_TYPE,
    NTP_SERVER,
    NTP_PORT,
    MAX_ACCEPTABLE_RTT,
    SYNC_DELAY,
    COMMAND_TIMEOUT,
    DOWNLOAD_CHUNK_SIZE,
)

__version__ = "2.0.0"

__all__ = [
    # Commands and Messages
    "CommandType",
    "CommandMessage",
    "StatusResponse",
    "StopRecordingResponse",
    "ErrorResponse",
    "FileResponse",
    "FileMetadata",
    "ListFilesResponse",
    "UploadStatus",
    "UploadItem",
    # Status
    "DeviceStatus",
    "DeviceType",
    # Constants
    "TCP_PORT",
    "SERVICE_TYPE",
    "NTP_SERVER",
    "NTP_PORT",
    "MAX_ACCEPTABLE_RTT",
    "SYNC_DELAY",
    "COMMAND_TIMEOUT",
    "DOWNLOAD_CHUNK_SIZE",
]
