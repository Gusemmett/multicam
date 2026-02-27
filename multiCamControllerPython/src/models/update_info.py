"""Update information data classes"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum
from datetime import datetime


class UpdateState(Enum):
    """Current state of the update process"""

    IDLE = "idle"
    CHECKING = "checking"
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    READY = "ready"
    APPLYING = "applying"
    ERROR = "error"


@dataclass
class ReleaseInfo:
    """Information about a release from S3"""

    version: str
    release_notes: str
    download_url: str
    file_size: int
    released_at: datetime
    dmg_key: str  # S3 object key for the DMG file
    min_version: Optional[str] = None  # Minimum version required to update


@dataclass
class UpdateProgress:
    """Download progress information"""

    bytes_downloaded: int
    total_bytes: int
    download_speed: float  # bytes per second

    @property
    def percent(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return (self.bytes_downloaded / self.total_bytes) * 100.0

    @property
    def eta_seconds(self) -> Optional[float]:
        if self.download_speed <= 0:
            return None
        remaining = self.total_bytes - self.bytes_downloaded
        return remaining / self.download_speed
