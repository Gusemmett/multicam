"""Video synchronization tool for multi-camera video alignment."""

__version__ = "1.0.0"

from .gui import SyncBench
from .core import TrackDecoder, SyncEngine
from .processing import VideoCutter, FFmpegCommandBuilder

__all__ = [
    'SyncBench',
    'TrackDecoder',
    'SyncEngine',
    'VideoCutter',
    'FFmpegCommandBuilder',
]
