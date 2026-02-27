"""
Network and protocol constants for MultiCam API.
"""

# Network Configuration
TCP_PORT = 8080
"""TCP port for device server"""

SERVICE_TYPE = "_multicam._tcp.local."
"""mDNS service type for device discovery"""

# NTP Configuration
NTP_SERVER = "pool.ntp.org"
"""NTP server for time synchronization"""

NTP_PORT = 123
"""NTP protocol port"""

MAX_ACCEPTABLE_RTT = 0.5
"""Maximum acceptable NTP round-trip time in seconds"""

# Synchronization
SYNC_DELAY = 3.0
"""Default delay for synchronized recording start (seconds)"""

# Timeouts
COMMAND_TIMEOUT = 60.0
"""Command timeout in seconds"""

DOWNLOAD_STALL_TIMEOUT = 600.0
"""Download stall timeout in seconds (10 minutes)"""

# Transfer Configuration
DOWNLOAD_CHUNK_SIZE = 8192
"""Chunk size for file downloads (bytes)"""

# File ID Format
FILE_ID_FORMAT = "{deviceId}_{timestamp}"
"""
File ID format pattern.

Example: Mountain-A1B2C3D4_1729000000123
"""

# Success Status Values (for backward compatibility)
SUCCESS_STATUSES = {
    "ready",
    "recording",
    "scheduled_recording_accepted",
    "command_received",
    "recording_stopped",
    "stopping",
}
"""Set of status values that indicate successful operations"""
