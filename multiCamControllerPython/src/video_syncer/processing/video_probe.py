"""Video metadata inspection using ffprobe."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import logging

from ..utils.ffmpeg_utils import get_ffprobe_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VideoProbeResult:
    """Metadata extracted via ffprobe for the primary video stream."""

    codec_name: str
    """Video codec name (e.g., 'h264', 'av1', 'hevc')"""
    width: int
    """Video width in pixels"""
    height: int
    """Video height in pixels"""
    format_name: str
    """Container format (e.g., 'mov,mp4,m4a,3gp,3g2,mj2')"""
    duration: Optional[float] = None
    """Duration in seconds, if available"""
    bit_rate: Optional[int] = None
    """Bit rate in bits/second, if available"""


def probe_video_stream(video_path: Path | str) -> VideoProbeResult:
    """
    Inspect video_path using ffprobe and return the first video stream metadata.

    Args:
        video_path: Path to the video file to inspect

    Returns:
        VideoProbeResult with extracted metadata

    Raises:
        RuntimeError: If ffprobe fails during inspection
        ValueError: If no valid video stream metadata is available
    """
    video_path = Path(video_path)

    if not video_path.exists():
        raise ValueError(f"Video file not found: {video_path}")

    ffprobe = get_ffprobe_path()
    ffprobe_cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,duration,bit_rate",
        "-show_entries",
        "format=format_name,duration",
        "-of",
        "json",
        str(video_path),
    ]

    logger.debug(f"Running ffprobe on {video_path.name}")

    try:
        process = subprocess.run(
            ffprobe_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe timed out while inspecting {video_path}")

    if process.returncode != 0:
        stderr_output = process.stderr.strip()
        raise RuntimeError(f"ffprobe failed when inspecting {video_path}: {stderr_output}")

    try:
        probe_data = json.loads(process.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse ffprobe output for {video_path}: {e}")

    # Extract stream info
    streams_raw = probe_data.get("streams", [])
    if not isinstance(streams_raw, list) or not streams_raw:
        raise ValueError(f"No video streams found in {video_path}")

    stream_info = streams_raw[0]
    if not isinstance(stream_info, dict):
        raise ValueError(f"Malformed ffprobe stream metadata for {video_path}")

    # Extract required fields
    codec_name = stream_info.get("codec_name")
    width = _coerce_int(stream_info.get("width"))
    height = _coerce_int(stream_info.get("height"))

    if codec_name is None or width is None or height is None:
        raise ValueError(f"Missing required stream metadata for {video_path}")

    # Extract format info
    format_obj = probe_data.get("format", {})
    format_name = format_obj.get("format_name") if isinstance(format_obj, dict) else None

    if format_name is None:
        raise ValueError(f"Missing format metadata for {video_path}")

    # Extract optional fields
    duration = _coerce_float(stream_info.get("duration"))
    if duration is None:
        # Try getting duration from format
        duration = _coerce_float(format_obj.get("duration"))

    bit_rate = _coerce_int(stream_info.get("bit_rate"))
    if bit_rate is None:
        # Try getting bit_rate from format
        bit_rate = _coerce_int(format_obj.get("bit_rate"))

    logger.debug(
        f"Probed {video_path.name}: {codec_name} {width}x{height}, "
        f"format={format_name}, duration={duration}s"
    )

    return VideoProbeResult(
        codec_name=codec_name,
        width=width,
        height=height,
        format_name=format_name,
        duration=duration,
        bit_rate=bit_rate,
    )


def format_tokens(format_name: str) -> set[str]:
    """
    Normalize the comma-separated ffprobe format name list.

    Args:
        format_name: Format name string from ffprobe (e.g., "mov,mp4,m4a")

    Returns:
        Set of normalized format tokens
    """
    return {token.strip().lower() for token in format_name.split(",") if token}


def _coerce_int(value: object) -> Optional[int]:
    """
    Attempt to convert ffprobe numeric fields to integers.

    Args:
        value: Value to coerce (could be int, float, str, or None)

    Returns:
        Integer value, or None if conversion fails
    """
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _coerce_float(value: object) -> Optional[float]:
    """
    Attempt to convert ffprobe numeric fields to floats.

    Args:
        value: Value to coerce (could be int, float, str, or None)

    Returns:
        Float value, or None if conversion fails
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def check_needs_reencode(
    video_path: Path | str,
    target_codec: str = "av1",
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
) -> tuple[bool, Optional[str]]:
    """
    Check if a video needs re-encoding based on target requirements.

    Args:
        video_path: Path to the video file
        target_codec: Target codec name (e.g., 'av1', 'h264')
        max_width: Maximum allowed width (None = no limit)
        max_height: Maximum allowed height (None = no limit)

    Returns:
        Tuple of (needs_reencode, reason)
        - needs_reencode: True if re-encoding is needed
        - reason: String describing why re-encoding is needed, or None
    """
    try:
        probe_result = probe_video_stream(video_path)
    except Exception as e:
        logger.warning(f"Failed to probe {video_path}: {e}")
        return False, None

    reasons = []

    # Check codec
    if probe_result.codec_name != target_codec:
        reasons.append(f"codec is {probe_result.codec_name}, not {target_codec}")

    # Check resolution
    if max_width and probe_result.width > max_width:
        reasons.append(f"width {probe_result.width} exceeds max {max_width}")

    if max_height and probe_result.height > max_height:
        reasons.append(f"height {probe_result.height} exceeds max {max_height}")

    if reasons:
        return True, "; ".join(reasons)

    return False, None
