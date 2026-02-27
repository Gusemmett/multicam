"""Generate sync_info.json from SyncBench tracks"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from dataclasses import asdict

from models.sync_info import (
    SyncInfo,
    SyncParameters,
    SingleTrackInfo,
    StereoTrackInfo
)

logger = logging.getLogger(__name__)


class SyncInfoGenerator:
    """Generates sync_info.json from SyncBench track data"""

    @staticmethod
    def generate(
        tracks: List[dict],
        sync_params: dict,
        s3_bucket: str,
        s3_prefix: str,
        temp_dir_to_s3_mapping: Dict[str, str]
    ) -> SyncInfo:
        """
        Generate SyncInfo from SyncBench track data.

        Args:
            tracks: List of track dictionaries from SyncBench
            sync_params: Sync parameters from SyncEngine.calculate_sync_parameters()
            s3_bucket: S3 bucket ID
            s3_prefix: S3 directory path
            temp_dir_to_s3_mapping: Mapping from temp file paths to S3 keys

        Returns:
            SyncInfo object
        """
        # Create sync parameters
        sync_parameters = SyncParameters(
            cut_times_us=sync_params["cut_times_us"],
            duration_us=sync_params["duration_us"],
            min_pre_sync_us=sync_params["min_pre_sync_us"]
        )

        # Process tracks
        track_infos = []
        reference_track_name = None

        for i, track in enumerate(tracks):
            is_reference = (i == 0)

            if track.get("stereo"):
                # Stereo track
                track_info = SyncInfoGenerator._create_stereo_track_info(
                    track, is_reference, temp_dir_to_s3_mapping
                )
            else:
                # Single track
                track_info = SyncInfoGenerator._create_single_track_info(
                    track, is_reference, temp_dir_to_s3_mapping
                )

            track_infos.append(track_info)

            # Set reference track name
            if is_reference:
                reference_track_name = track_info["file_path"]

        # Create SyncInfo
        sync_info = SyncInfo(
            version="1.0",
            created_at=datetime.utcnow().isoformat() + "Z",
            s3_bucket=s3_bucket,
            s3_prefix=s3_prefix,
            reference_track=reference_track_name,
            sync_parameters=sync_parameters,
            tracks=track_infos
        )

        return sync_info

    @staticmethod
    def _create_single_track_info(
        track: dict,
        is_reference: bool,
        temp_to_s3_mapping: Dict[str, str]
    ) -> dict:
        """Create info for single video track"""
        # Get temp path
        temp_path = track.get("path")

        # Get S3 key from mapping
        s3_key = temp_to_s3_mapping.get(temp_path, "")

        # Get relative file path (just filename)
        file_path = Path(temp_path).name if temp_path else ""

        track_info = SingleTrackInfo(
            file_path=file_path,
            s3_key=s3_key,
            sync_cut_time_us=track.get("sync_cut_time_us", 0),
            cut_start_us=track.get("cut_start_us"),
            cut_end_us=track.get("cut_end_us"),
            is_reference=is_reference
        )

        return asdict(track_info)

    @staticmethod
    def _create_stereo_track_info(
        track: dict,
        is_reference: bool,
        temp_to_s3_mapping: Dict[str, str]
    ) -> dict:
        """Create info for stereo video track"""
        # Get stereo paths
        left_path = track.get("path_left", "")
        right_path = track.get("path_right", "")
        rgb_path = track.get("path_rgb")

        # Build S3 keys dict
        s3_keys = {
            "left": temp_to_s3_mapping.get(left_path, ""),
            "right": temp_to_s3_mapping.get(right_path, "")
        }

        if rgb_path:
            s3_keys["rgb"] = temp_to_s3_mapping.get(rgb_path, "")

        # Get directory name from left path
        if left_path:
            dir_path = str(Path(left_path).parent.name) + "/"
        else:
            dir_path = ""

        track_info = StereoTrackInfo(
            file_path=dir_path,
            s3_keys=s3_keys,
            sync_cut_time_us=track.get("sync_cut_time_us", 0),
            cut_start_us=track.get("cut_start_us"),
            cut_end_us=track.get("cut_end_us"),
            is_reference=is_reference
        )

        return asdict(track_info)

    @staticmethod
    def create_temp_to_s3_mapping(
        temp_dir: str,
        s3_prefix: str,
        video_files: List[str]
    ) -> Dict[str, str]:
        """
        Create mapping from temp file paths to S3 keys.

        Args:
            temp_dir: Temporary directory path
            s3_prefix: S3 prefix (e.g., "2025-01-15/session_123/")
            video_files: List of video file paths (relative to temp_dir)

        Returns:
            Dictionary mapping temp file path to S3 key
        """
        temp_dir_path = Path(temp_dir)
        mapping = {}

        for video_file in video_files:
            # Convert to Path
            video_path = Path(video_file)

            # Get full temp path
            if video_path.is_absolute():
                temp_path = str(video_path)
            else:
                temp_path = str(temp_dir_path / video_path)

            # Build S3 key by reconstructing the structure
            # Get relative path from temp_dir
            try:
                rel_path = Path(temp_path).relative_to(temp_dir_path)
                s3_key = s3_prefix + str(rel_path).replace('\\', '/')
            except ValueError:
                # If path is not relative to temp_dir, just use filename
                s3_key = s3_prefix + Path(temp_path).name

            mapping[temp_path] = s3_key

        logger.debug(f"Created temp-to-S3 mapping with {len(mapping)} entries")
        return mapping
