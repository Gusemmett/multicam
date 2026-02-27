"""
Utilities for parsing session directory structures to find sync groups.

A sync group is a directory containing video files that should be synced together.
"""

from pathlib import Path
from typing import List, Set, Union
import logging

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {'.mov', '.mp4'}


def find_sync_groups_local(root_path: Union[str, Path], max_depth: int = 3) -> List[Path]:
    """
    Recursively find all directories containing video files (sync groups) in a local filesystem.

    Args:
        root_path: Root directory to scan
        max_depth: Maximum recursion depth (default 3)

    Returns:
        List of directory paths that contain video files

    Raises:
        ValueError: If a directory contains both videos and subdirectories (videos must be in leaf nodes)
    """
    root_path = Path(root_path)
    sync_groups = []

    def scan_directory(current_path: Path, current_depth: int):
        if current_depth > max_depth:
            return

        if not current_path.is_dir():
            return

        # Find all items in current directory
        try:
            items = list(current_path.iterdir())
        except PermissionError:
            logger.warning(f"Permission denied accessing {current_path}")
            return

        # Separate files and directories
        video_files = [f for f in items if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]
        subdirectories = [d for d in items if d.is_dir() and not d.name.startswith('.')]

        # Check if this directory has videos
        if video_files:
            # Validate: videos should only be in leaf nodes
            if subdirectories:
                raise ValueError(
                    f"Directory {current_path} contains both videos and subdirectories. "
                    f"Videos must be in leaf directories only. "
                    f"Found {len(video_files)} videos and {len(subdirectories)} subdirectories."
                )

            # This is a sync group
            sync_groups.append(current_path)
            logger.info(f"Found sync group: {current_path} with {len(video_files)} videos")
        else:
            # No videos in this directory, recurse into subdirectories
            for subdir in subdirectories:
                scan_directory(subdir, current_depth + 1)

    scan_directory(root_path, 0)
    return sync_groups


def find_sync_groups_s3(s3_keys: List[str], prefix: str = "") -> List[str]:
    """
    Find all directories containing video files from a list of S3 object keys.

    Args:
        s3_keys: List of S3 object keys
        prefix: Optional prefix to strip from keys (e.g., "bucket/path/to/session/")

    Returns:
        List of directory paths (relative to prefix) that contain video files

    Raises:
        ValueError: If a directory contains both videos and subdirectories
    """
    # Build directory structure from S3 keys
    directory_structure = {}  # Maps directory path -> {'videos': [...], 'subdirs': set()}

    for key in s3_keys:
        # Strip prefix if provided
        if prefix and key.startswith(prefix):
            rel_key = key[len(prefix):]
        else:
            rel_key = key

        # Skip if empty or doesn't end with video extension
        if not rel_key or not any(rel_key.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
            continue

        # Extract directory path
        if '/' in rel_key:
            dir_path = rel_key.rsplit('/', 1)[0]
        else:
            dir_path = ""  # Root directory

        # Initialize directory structure if needed
        if dir_path not in directory_structure:
            directory_structure[dir_path] = {'videos': [], 'subdirs': set()}

        # Add video to this directory
        directory_structure[dir_path]['videos'].append(rel_key)

    # Build subdirectory relationships
    for dir_path in list(directory_structure.keys()):
        if not dir_path:  # Skip root
            continue

        # Find parent directory
        parts = dir_path.split('/')
        for i in range(len(parts)):
            parent_path = '/'.join(parts[:i]) if i > 0 else ""

            if parent_path in directory_structure or parent_path == "":
                # Ensure parent exists
                if parent_path not in directory_structure:
                    directory_structure[parent_path] = {'videos': [], 'subdirs': set()}

                # Add as subdirectory to parent
                child = '/'.join(parts[:i+1])
                if child in directory_structure:
                    directory_structure[parent_path]['subdirs'].add(child)

    # Validate and collect sync groups
    sync_groups = []

    for dir_path, info in directory_structure.items():
        if info['videos']:
            # This directory has videos
            if info['subdirs']:
                raise ValueError(
                    f"S3 directory '{dir_path}' contains both videos and subdirectories. "
                    f"Videos must be in leaf directories only. "
                    f"Found {len(info['videos'])} videos and {len(info['subdirs'])} subdirectories."
                )

            sync_groups.append(dir_path if dir_path else ".")
            logger.info(f"Found S3 sync group: {dir_path or 'root'} with {len(info['videos'])} videos")

    # Check depth limit (max 3 levels)
    for group in sync_groups:
        depth = group.count('/') + (1 if group and group != "." else 0)
        if depth > 3:
            logger.warning(f"Sync group '{group}' exceeds max depth of 3 (depth={depth})")

    return sync_groups
