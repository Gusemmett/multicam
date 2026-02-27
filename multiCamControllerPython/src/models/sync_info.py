"""Data models for video sync information"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, List
from datetime import datetime
import json


@dataclass
class SyncParameters:
    """Sync parameters from SyncEngine"""
    cut_times_us: List[int]
    """List of cut start times for each video (microseconds)"""

    duration_us: int
    """Final output duration (microseconds)"""

    min_pre_sync_us: int
    """Minimum pre-sync content (microseconds)"""


@dataclass
class SingleTrackInfo:
    """Information for a single video track"""
    file_path: str
    """Relative file path"""

    s3_key: str
    """Full S3 key"""

    sync_cut_time_us: int
    """Sync point time in microseconds"""

    cut_start_us: Optional[int]
    """Cut start time (microseconds), None if not set"""

    cut_end_us: Optional[int]
    """Cut end time (microseconds), None if not set"""

    is_reference: bool
    """True if this is the reference track"""

    type: str = "single"
    """Track type: 'single'"""


@dataclass
class StereoTrackInfo:
    """Information for a stereo video track"""
    file_path: str
    """Relative directory path"""

    s3_keys: Dict[str, str]
    """S3 keys for left, right, and optionally rgb"""

    sync_cut_time_us: int
    """Sync point time in microseconds"""

    cut_start_us: Optional[int]
    """Cut start time (microseconds), None if not set"""

    cut_end_us: Optional[int]
    """Cut end time (microseconds), None if not set"""

    is_reference: bool
    """True if this is the reference track"""

    type: str = "stereo"
    """Track type: 'stereo'"""


@dataclass
class SyncInfo:
    """Complete sync information for video processing"""
    version: str
    """Format version"""

    created_at: str
    """ISO timestamp of creation"""

    s3_bucket: str
    """Source S3 bucket ID"""

    s3_prefix: str
    """S3 directory path"""

    reference_track: str
    """Reference track file path"""

    sync_parameters: SyncParameters
    """Sync parameters from SyncEngine"""

    tracks: List[dict]
    """List of track info (SingleTrackInfo or StereoTrackInfo as dicts)"""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "version": self.version,
            "created_at": self.created_at,
            "s3_bucket": self.s3_bucket,
            "s3_prefix": self.s3_prefix,
            "reference_track": self.reference_track,
            "sync_parameters": asdict(self.sync_parameters),
            "tracks": self.tracks
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "SyncInfo":
        """Create from dictionary"""
        return cls(
            version=data["version"],
            created_at=data["created_at"],
            s3_bucket=data["s3_bucket"],
            s3_prefix=data["s3_prefix"],
            reference_track=data["reference_track"],
            sync_parameters=SyncParameters(**data["sync_parameters"]),
            tracks=data["tracks"]
        )

    @classmethod
    def from_json(cls, json_str: str) -> "SyncInfo":
        """Create from JSON string"""
        data = json.loads(json_str)
        return cls.from_dict(data)
