"""Utilities for finding FFmpeg binaries in bundled app."""

import os
import sys
import shutil
from pathlib import Path


def get_ffmpeg_path() -> str:
    """
    Get path to ffmpeg binary (bundled or system).

    Returns:
        Path to ffmpeg binary

    Raises:
        RuntimeError: If ffmpeg is not found
    """
    # If running as bundled app (PyInstaller)
    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle
        bundle_dir = Path(sys._MEIPASS)
        ffmpeg_path = bundle_dir / 'ffmpeg_bins' / 'ffmpeg'

        if ffmpeg_path.exists():
            # Make sure it's executable
            os.chmod(ffmpeg_path, 0o755)
            return str(ffmpeg_path)

    # Fall back to system ffmpeg
    system_ffmpeg = shutil.which('ffmpeg')
    if system_ffmpeg:
        return system_ffmpeg

    raise RuntimeError(
        "FFmpeg not found. Please install FFmpeg or ensure it's in your PATH."
    )


def get_ffprobe_path() -> str:
    """
    Get path to ffprobe binary (bundled or system).

    Returns:
        Path to ffprobe binary

    Raises:
        RuntimeError: If ffprobe is not found
    """
    # If running as bundled app (PyInstaller)
    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle
        bundle_dir = Path(sys._MEIPASS)
        ffprobe_path = bundle_dir / 'ffmpeg_bins' / 'ffprobe'

        if ffprobe_path.exists():
            # Make sure it's executable
            os.chmod(ffprobe_path, 0o755)
            return str(ffprobe_path)

    # Fall back to system ffprobe
    system_ffprobe = shutil.which('ffprobe')
    if system_ffprobe:
        return system_ffprobe

    raise RuntimeError(
        "FFprobe not found. Please install FFmpeg or ensure it's in your PATH."
    )
