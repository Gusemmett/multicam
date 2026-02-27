"""File utility functions for handling downloads and archives."""

import zipfile
import logging
import subprocess
import platform
import json
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def is_zip_file(file_path: str) -> bool:
    """
    Check if a file is a valid ZIP archive.

    Args:
        file_path: Path to the file to check

    Returns:
        True if the file is a valid ZIP archive, False otherwise
    """
    try:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return False

        # Check by extension first (fast check)
        if path.suffix.lower() == '.zip':
            # Verify it's actually a valid zip
            return zipfile.is_zipfile(file_path)

        return False
    except Exception as e:
        logger.warning(f"Error checking if {file_path} is zip: {e}")
        return False


def unpack_zip_file(zip_path: str, extract_to: Optional[str] = None) -> Optional[str]:
    """
    Unpack a ZIP file to a directory.

    Args:
        zip_path: Path to the ZIP file
        extract_to: Optional directory to extract to. If None, extracts to a directory
                   with the same name as the zip file (without extension) in the same location.

    Returns:
        Path to the extraction directory if successful, None otherwise
    """
    try:
        zip_file_path = Path(zip_path)

        if not zip_file_path.exists():
            logger.error(f"ZIP file not found: {zip_path}")
            return None

        # Determine extraction directory
        if extract_to:
            extraction_dir = Path(extract_to)
        else:
            # Extract to directory with same name as zip (without extension)
            extraction_dir = zip_file_path.parent / zip_file_path.stem

        # Create extraction directory
        extraction_dir.mkdir(parents=True, exist_ok=True)

        # Extract zip file
        logger.info(f"Unpacking {zip_file_path.name} to {extraction_dir}")

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Get list of files in zip
            file_list = zip_ref.namelist()
            logger.info(f"   Found {len(file_list)} files in archive")

            # Extract all files
            zip_ref.extractall(extraction_dir)

        logger.info(f"Successfully unpacked to {extraction_dir}")
        return str(extraction_dir)

    except zipfile.BadZipFile:
        logger.error(f"Invalid ZIP file: {zip_path}")
        return None
    except Exception as e:
        logger.error(f"Error unpacking {zip_path}: {e}")
        return None


def get_unpacked_path(file_path: str, delete_zip_after_unpack: bool = False) -> str:
    """
    Get the path to use for video syncing. If the file is a ZIP, unpack it and return
    the directory path. Otherwise, return the original file path.

    This is the main entry point for handling potentially zipped files.

    Args:
        file_path: Path to a file (could be .zip or video file)
        delete_zip_after_unpack: If True, delete the ZIP file after successful unpacking

    Returns:
        Path to use for video syncing (directory for unpacked zips, or original file path)
    """
    if is_zip_file(file_path):
        logger.info(f"Detected ZIP file: {file_path}")
        unpacked_dir = unpack_zip_file(file_path)

        if unpacked_dir:
            logger.info(f"Using unpacked directory: {unpacked_dir}")

            # Delete ZIP file if requested
            if delete_zip_after_unpack:
                cleanup_zip_after_unpack(file_path, keep_zip=False)

            return unpacked_dir
        else:
            logger.warning(f"Failed to unpack ZIP, using original path: {file_path}")
            return file_path

    return file_path


def cleanup_zip_after_unpack(zip_path: str, keep_zip: bool = False) -> None:
    """
    Optionally remove the original ZIP file after successful unpacking.

    Args:
        zip_path: Path to the ZIP file
        keep_zip: If True, keep the original ZIP file. If False, delete it.
    """
    if not keep_zip:
        try:
            Path(zip_path).unlink()
            logger.info(f"Removed original ZIP file: {zip_path}")
        except Exception as e:
            logger.warning(f"Could not remove ZIP file {zip_path}: {e}")


def open_folder_in_explorer(folder_path: str) -> bool:
    """
    Open a folder in the system's file explorer (Finder on macOS, Explorer on Windows).

    Args:
        folder_path: Path to the folder to open

    Returns:
        True if successful, False otherwise
    """
    try:
        path = Path(folder_path)
        if not path.exists():
            logger.error(f"Folder does not exist: {folder_path}")
            return False

        system = platform.system()

        if system == "Darwin":  # macOS
            subprocess.run(["open", str(path)], check=True)
        elif system == "Windows":
            subprocess.run(["explorer", str(path)], check=True)
        elif system == "Linux":
            subprocess.run(["xdg-open", str(path)], check=True)
        else:
            logger.error(f"Unsupported platform: {system}")
            return False

        logger.info(f"Opened folder: {folder_path}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to open folder {folder_path}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error opening folder {folder_path}: {e}")
        return False


def check_mov_codecs_compatible_with_mp4(mov_path: Path) -> tuple[bool, Optional[str]]:
    """
    Check if a .mov file's codecs are compatible with MP4 container.

    Compatible codecs:
    - Video: h264, h265, hevc, av1, mpeg4, mpeg2video
    - Audio: aac, mp3, ac3, eac3

    Args:
        mov_path: Path to the .mov file

    Returns:
        Tuple of (is_compatible, reason)
        - is_compatible: True if codecs are compatible with MP4
        - reason: String describing incompatibility, or None if compatible
    """
    try:
        # Import here to avoid circular dependency
        from video_syncer.utils.ffmpeg_utils import get_ffprobe_path

        ffprobe = get_ffprobe_path()

        # Probe the file to get codec information
        cmd = [
            ffprobe,
            "-v", "error",
            "-select_streams", "v:0,a:0",
            "-show_entries", "stream=codec_name,codec_type",
            "-of", "json",
            str(mov_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            logger.warning(f"ffprobe failed for {mov_path.name}: {result.stderr}")
            return False, f"ffprobe failed: {result.stderr}"

        data = json.loads(result.stdout)
        streams = data.get("streams", [])

        if not streams:
            return False, "No streams found"

        # Define compatible codecs
        compatible_video_codecs = {"h264", "h265", "hevc", "av1", "mpeg4", "mpeg2video"}
        compatible_audio_codecs = {"aac", "mp3", "ac3", "eac3"}

        video_codec = None
        audio_codec = None

        for stream in streams:
            codec_type = stream.get("codec_type")
            codec_name = stream.get("codec_name")

            if codec_type == "video" and not video_codec:
                video_codec = codec_name
            elif codec_type == "audio" and not audio_codec:
                audio_codec = codec_name

        # Check video codec
        if video_codec and video_codec not in compatible_video_codecs:
            return False, f"Video codec '{video_codec}' is not compatible with MP4"

        # Check audio codec (optional, some files might not have audio)
        if audio_codec and audio_codec not in compatible_audio_codecs:
            return False, f"Audio codec '{audio_codec}' is not compatible with MP4"

        logger.debug(f"{mov_path.name}: video={video_codec}, audio={audio_codec} - compatible with MP4")
        return True, None

    except subprocess.TimeoutExpired:
        return False, "ffprobe timed out"
    except json.JSONDecodeError as e:
        return False, f"Failed to parse ffprobe output: {e}"
    except Exception as e:
        logger.error(f"Error checking codecs for {mov_path}: {e}")
        return False, str(e)


def remux_mov_to_mp4(mov_path: Path) -> Optional[Path]:
    """
    Remux a .mov file to .mp4 format (no re-encoding, just container change).

    The remux is done to a temporary file first, then the original .mov is replaced.
    Note: Cannot remux in-place, so we use a temp file.

    Args:
        mov_path: Path to the .mov file

    Returns:
        Path to the new .mp4 file (same location as original), or None if failed
    """
    try:
        # Import here to avoid circular dependency
        from video_syncer.utils.ffmpeg_utils import get_ffmpeg_path

        # First check if codecs are compatible
        is_compatible, reason = check_mov_codecs_compatible_with_mp4(mov_path)

        if not is_compatible:
            logger.warning(f"Cannot remux {mov_path.name} to MP4: {reason}")
            return None

        logger.info(f"Remuxing {mov_path.name} to MP4 format...")

        ffmpeg = get_ffmpeg_path()

        # Create temp file in same directory with .tmp.mp4 extension
        temp_mp4 = mov_path.with_suffix(".tmp.mp4")
        final_mp4 = mov_path.with_suffix(".mp4")

        # Build ffmpeg command (copy codecs, no re-encoding)
        cmd = [
            ffmpeg,
            "-i", str(mov_path),
            "-c", "copy",  # Copy all streams without re-encoding
            "-movflags", "+faststart",  # Optimize for streaming
            "-y",  # Overwrite output file if exists
            str(temp_mp4)
        ]

        # Run ffmpeg
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode != 0:
            logger.error(f"ffmpeg remux failed for {mov_path.name}: {result.stderr}")
            # Clean up temp file if it exists
            if temp_mp4.exists():
                temp_mp4.unlink()
            return None

        # Verify temp file was created
        if not temp_mp4.exists():
            logger.error(f"Remux output file not created: {temp_mp4}")
            return None

        # Remove original .mov file
        try:
            mov_path.unlink()
            logger.debug(f"Removed original .mov file: {mov_path}")
        except Exception as e:
            logger.warning(f"Could not remove original .mov file {mov_path}: {e}")
            # Continue anyway, we'll rename the temp file

        # Rename temp file to final .mp4 name
        temp_mp4.rename(final_mp4)
        logger.info(f"Successfully remuxed to {final_mp4.name}")

        return final_mp4

    except subprocess.TimeoutExpired:
        logger.error(f"ffmpeg remux timed out for {mov_path.name}")
        # Clean up temp file
        temp_mp4 = mov_path.with_suffix(".tmp.mp4")
        if temp_mp4.exists():
            temp_mp4.unlink()
        return None
    except Exception as e:
        logger.error(f"Error remuxing {mov_path.name}: {e}")
        # Clean up temp file
        temp_mp4 = mov_path.with_suffix(".tmp.mp4")
        if temp_mp4.exists():
            temp_mp4.unlink()
        return None


def process_mov_files(path: str) -> None:
    """
    Process all .mov files in a given path (file or directory) and remux them to .mp4.

    This function:
    1. Finds all .mov files (recursively if path is a directory)
    2. Checks if their codecs are compatible with MP4
    3. Remuxes compatible .mov files to .mp4
    4. Replaces the original .mov files

    Args:
        path: Path to a file or directory to process
    """
    path_obj = Path(path)

    if not path_obj.exists():
        logger.warning(f"Path does not exist: {path}")
        return

    # Collect all .mov files
    mov_files = []

    if path_obj.is_file() and path_obj.suffix.lower() == ".mov":
        mov_files.append(path_obj)
    elif path_obj.is_dir():
        # Recursively find all .mov files
        mov_files = list(path_obj.rglob("*.mov"))
        mov_files.extend(list(path_obj.rglob("*.MOV")))

    if not mov_files:
        logger.debug(f"No .mov files found in {path}")
        return

    logger.info(f"Found {len(mov_files)} .mov file(s) to process")

    # Process each .mov file
    successful = 0
    skipped = 0
    failed = 0

    for mov_file in mov_files:
        logger.info(f"Processing {mov_file.name}...")

        result = remux_mov_to_mp4(mov_file)

        if result:
            successful += 1
        elif check_mov_codecs_compatible_with_mp4(mov_file)[0] is False:
            # Codecs not compatible, skip
            skipped += 1
            logger.info(f"Skipped {mov_file.name} (incompatible codecs)")
        else:
            # Remux failed for other reason
            failed += 1

    logger.info(
        f"Finished processing .mov files: {successful} remuxed, "
        f"{skipped} skipped (incompatible), {failed} failed"
    )
