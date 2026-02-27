"""RRD (Rerun) packaging for synced multi-camera videos."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import rerun as rr
import rerun.blueprint as rrb
from natsort import natsorted

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VideoIngestEntry:
    """Structured container coupling a source video with its camera/video entity paths."""

    source_path: Path
    """Filesystem path of the input video on disk."""
    camera_log_path: str
    """Root Rerun entity path for this camera (e.g. '/world/exo/cam0')."""
    video_log_path: str
    """Rerun entity path for the video stream (e.g. '/world/exo/cam0/pinhole/video')."""

    @property
    def pinhole_log_path(self) -> str:
        """Rerun entity path for the camera's pinhole node."""
        return f"{self.camera_log_path}/pinhole"


def organize_synced_videos(
    synced_files: dict[str, str]
) -> tuple[list[Path], list[Path]]:
    """
    Categorize synced videos into exo (exocentric) and ego (egocentric) based on file structure.

    Strategy (matching simplecv behavior):
    1. Videos in subdirectories (unpacked from .zip) → EGO
       - These are stereo pairs: left.mp4, right.mp4, rgb.mp4
    2. Videos directly in session root directory → EXO
       - These are single camera videos

    This matches the expected structure:
    - session_dir/
      - cam1.mp4 (EXO)
      - cam2.mp4 (EXO)
      - ego_device/  (unpacked from .zip)
        - left.mp4 (EGO)
        - right.mp4 (EGO)
        - rgb.mp4 (EGO)

    Args:
        synced_files: Dictionary mapping original paths to synced paths

    Returns:
        Tuple of (exo_videos, ego_videos) as lists of Path objects
    """
    exo_videos: list[Path] = []
    ego_videos: list[Path] = []

    # First, determine the session directory by finding common parent
    all_paths = [Path(p) for p in synced_files.values()]
    if not all_paths:
        return exo_videos, ego_videos

    # Get session directory (should be the common parent of all files)
    first_path = all_paths[0]
    if first_path.is_dir():
        # If path is a directory, use its parent as session dir
        session_dir = first_path.parent
    else:
        # If path is a file, use its parent as session dir
        session_dir = first_path.parent

    logger.info(f"Detected session directory: {session_dir}")

    for synced_path in synced_files.values():
        path = Path(synced_path)

        if path.is_dir():
            # This is a directory (unpacked stereo pair from .zip) → EGO
            logger.info(f"Categorized {path.name} as EGO (subdirectory with stereo pair)")
            ego_videos.append(path)
        elif path.parent == session_dir:
            # This video is directly in the session root directory → EXO
            logger.info(f"Categorized {path.name} as EXO (root directory video)")
            exo_videos.append(path)
        else:
            # This video is in a subdirectory → EGO
            # (could be individual files from unpacked stereo directory)
            logger.info(f"Categorized {path.name} as EGO (in subdirectory: {path.parent.name})")
            ego_videos.append(path)

    logger.info(f"Organization complete: {len(exo_videos)} EXO, {len(ego_videos)} EGO")
    return exo_videos, ego_videos


def collect_video_files_from_path(video_path: Path) -> list[Path]:
    """
    Collect video files from a path (either a single video or directory with stereo pair).

    Supports both .mp4 and .mov files.

    Args:
        video_path: Path to video file or directory

    Returns:
        List of video file paths
    """
    if video_path.is_dir():
        # Collect all MP4 and MOV files in directory (left, right, rgb, etc.)
        video_files = []
        video_files.extend(video_path.glob("*.mp4"))
        video_files.extend(video_path.glob("*.mov"))
        video_files.extend(video_path.glob("*.MP4"))
        video_files.extend(video_path.glob("*.MOV"))
        video_files = natsorted(video_files)
        logger.debug(f"Found {len(video_files)} video(s) in {video_path.name}")
        return video_files
    else:
        # Single video file
        return [video_path]


def create_video_entries(
    video_paths: list[Path],
    log_root: str
) -> list[VideoIngestEntry]:
    """
    Build VideoIngestEntry for each video file or directory.

    Args:
        video_paths: List of video file paths or directories
        log_root: Root entity path (e.g., "/world/exo" or "/world/ego")

    Returns:
        List of VideoIngestEntry objects
    """
    video_entries: list[VideoIngestEntry] = []

    for video_path in video_paths:
        if video_path.is_dir():
            # Handle stereo pair directory
            video_files = collect_video_files_from_path(video_path)
            for video_file in video_files:
                # Create entity like: /world/ego/stereo0/left
                camera_name = video_file.stem  # "left", "right", "rgb"
                camera_log_path = f"{log_root}/{video_path.name}/{camera_name}"
                video_log_path = f"{camera_log_path}/pinhole/video"

                entry = VideoIngestEntry(
                    source_path=video_file,
                    camera_log_path=camera_log_path,
                    video_log_path=video_log_path,
                )
                video_entries.append(entry)
                logger.debug(f"Created entry: {video_log_path}")
        else:
            # Handle single video file
            # Create entity like: /world/exo/cam0
            camera_name = video_path.stem
            camera_log_path = f"{log_root}/{camera_name}"
            video_log_path = f"{camera_log_path}/pinhole/video"

            entry = VideoIngestEntry(
                source_path=video_path,
                camera_log_path=camera_log_path,
                video_log_path=video_log_path,
            )
            video_entries.append(entry)
            logger.debug(f"Created entry: {video_log_path}")

    return video_entries


def log_videos_to_rrd(
    video_entries: list[VideoIngestEntry],
    timeline: str = "video_time"
) -> list[str]:
    """
    Log videos to Rerun using AssetVideo.

    Args:
        video_entries: List of video entries to log
        timeline: Timeline name for video playback

    Returns:
        List of pinhole log paths that were logged
    """
    logged_pinhole_paths: list[str] = []

    for entry in video_entries:
        try:
            # Log video asset which is referred to by frame references
            video_asset = rr.AssetVideo(path=entry.source_path)
            rr.log(entry.video_log_path, video_asset, static=True)

            # Send automatically determined video frame timestamps
            frame_timestamps_ns = video_asset.read_frame_timestamps_nanos()

            rr.send_columns(
                entry.video_log_path,
                # Timeline values match video timestamps
                indexes=[rr.TimeColumn(timeline, duration=1e-9 * frame_timestamps_ns)],
                columns=rr.VideoFrameReference.columns_nanos(frame_timestamps_ns),
            )

            logged_pinhole_paths.append(entry.pinhole_log_path)
            logger.info(f"Logged video: {entry.video_log_path}")

        except Exception as e:
            logger.error(f"Failed to log video {entry.source_path}: {e}")

    return logged_pinhole_paths


def create_blueprint(
    exo_pinhole_paths: list[str],
    ego_pinhole_paths: list[str]
) -> rrb.Blueprint:
    """
    Generate Rerun visualization layout.

    Layout:
    - Center: 3D view
    - Bottom: Exo videos (horizontal row)
    - Right: Ego videos (vertical column)

    Args:
        exo_pinhole_paths: List of exo camera pinhole entity paths
        ego_pinhole_paths: List of ego camera pinhole entity paths

    Returns:
        Rerun Blueprint object
    """
    # Start with main 3D view
    main_view = rrb.Spatial3DView(origin="/")

    # Add ego videos on the right (vertical column)
    if ego_pinhole_paths:
        ego_views = [
            rrb.Tabs(
                rrb.Spatial2DView(origin=pinhole_path),
            )
            for pinhole_path in ego_pinhole_paths
        ]
        main_view = rrb.Horizontal(
            contents=[
                main_view,
                rrb.Vertical(contents=ego_views),
            ],
            column_shares=[4, 1],
        )

    # Add exo videos on the bottom (horizontal row)
    if exo_pinhole_paths:
        exo_views = [
            rrb.Tabs(
                rrb.Spatial2DView(origin=pinhole_path),
            )
            for pinhole_path in exo_pinhole_paths
        ]
        main_view = rrb.Vertical(
            contents=[
                main_view,
                rrb.Horizontal(contents=exo_views),
            ],
            row_shares=[4, 1],
        )

    blueprint = rrb.Blueprint(main_view, collapse_panels=True)
    return blueprint


def package_to_rrd(
    synced_files: dict[str, str],
    output_path: str,
    application_id: str = "MultiCamController"
) -> bool:
    """
    Package synced videos into a Rerun RRD file.

    Args:
        synced_files: Dictionary mapping original paths to synced paths
        output_path: Path where RRD file will be saved
        application_id: Application identifier for Rerun

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Starting RRD packaging: {len(synced_files)} videos")

        # Initialize Rerun
        rr.init(application_id=application_id, default_enabled=True, strict=True)

        # Organize videos into exo/ego
        exo_videos, ego_videos = organize_synced_videos(synced_files)

        # Create video entries for each category
        exo_entries = create_video_entries(exo_videos, "/world/exo") if exo_videos else []
        ego_entries = create_video_entries(ego_videos, "/world/ego") if ego_videos else []

        all_entries = exo_entries + ego_entries

        if not all_entries:
            logger.warning("No video entries to log")
            return False

        logger.info(f"Logging {len(all_entries)} video entries to RRD")

        # Log videos to Rerun
        exo_pinhole_paths = log_videos_to_rrd(exo_entries) if exo_entries else []
        ego_pinhole_paths = log_videos_to_rrd(ego_entries) if ego_entries else []

        # Create and send blueprint
        blueprint = create_blueprint(exo_pinhole_paths, ego_pinhole_paths)
        rr.send_blueprint(blueprint)

        # Save RRD file
        rr.save(output_path)
        logger.info(f"Successfully saved RRD to: {output_path}")

        return True

    except Exception as e:
        logger.error(f"Failed to package RRD: {e}", exc_info=True)
        return False
