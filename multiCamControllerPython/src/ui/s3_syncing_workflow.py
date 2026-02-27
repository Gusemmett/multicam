"""S3 video syncing workflow with partial downloads"""

import logging
import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from services.s3_manager import S3Manager
from models.app_settings import AppSettings
from video_syncer.gui.main_window import SyncBench
from video_syncer.core.sync_engine import SyncEngine
from utils.sync_info_generator import SyncInfoGenerator
from utils.constants import RESOLUTION_DIMENSIONS
from utils.session_parser import find_sync_groups_s3, find_sync_groups_local

logger = logging.getLogger(__name__)


class S3SyncingWorkflow(QObject):
    """Manages S3 video syncing workflow with partial downloads"""

    # Signals
    workflow_cancelled = Signal()
    workflow_completed = Signal(str)  # sync_info.json S3 key
    download_progress = Signal(int, int)  # current, total

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.s3_manager = None
        self.temp_dir = None
        self.sync_bench = None
        self.s3_bucket = None
        self.s3_prefix = None
        self.temp_to_s3_mapping = {}
        self.job_id = None  # Track job ID for auto mode

    async def start_workflow(self, s3_bucket: str, s3_prefix: str, job_id: str = None):
        """
        Start S3 syncing workflow.

        Args:
            s3_bucket: S3 bucket ID
            s3_prefix: S3 directory path
            job_id: Optional job ID for auto mode
        """
        self.s3_bucket = s3_bucket
        self.s3_prefix = s3_prefix
        self.job_id = job_id

        # Create S3 manager
        self.s3_manager = S3Manager(bucket_name=s3_bucket)

        # Test S3 connection
        if not await self.s3_manager.test_connection():
            QMessageBox.critical(
                None,
                "S3 Connection Failed",
                f"Failed to connect to S3 bucket: {s3_bucket}\n\n"
                "Please check your credentials and bucket configuration."
            )
            if self.job_id:
                self.abandon_job()
            self.workflow_cancelled.emit()
            return

        try:
            # Step 1: List S3 directory
            sync_groups = await self.list_s3_videos()

            if not sync_groups:
                QMessageBox.warning(
                    None,
                    "No Videos Found",
                    f"No video files found in S3 path:\n{s3_prefix}\n\n"
                    "Please check the path and try again."
                )
                if self.job_id:
                    self.abandon_job()
                self.workflow_cancelled.emit()
                return

            # Step 2: Download partial videos
            success = await self.download_partial_videos(sync_groups)

            if not success:
                QMessageBox.critical(
                    None,
                    "Download Failed",
                    "Failed to download videos from S3.\n\n"
                    "Check the logs for details."
                )
                self.cleanup_temp_files()
                if self.job_id:
                    self.abandon_job()
                self.workflow_cancelled.emit()
                return

            # Step 3: Launch SyncBench
            self.launch_sync_bench()

        except Exception as e:
            logger.error(f"S3 syncing workflow failed: {e}")
            QMessageBox.critical(
                None,
                "Workflow Error",
                f"An error occurred during the syncing workflow:\n{str(e)}"
            )
            self.cleanup_temp_files()
            if self.job_id:
                self.abandon_job()
            self.workflow_cancelled.emit()

    async def list_s3_videos(self) -> List[str]:
        """
        List and find sync groups in S3 directory using recursive scanning.

        Returns:
            List of directory paths (relative to prefix) that contain video files
        """
        logger.info(f"Listing S3 directory: {self.s3_prefix}")

        objects = await self.s3_manager.list_directory(self.s3_prefix)

        # Extract S3 keys
        s3_keys = [obj['Key'] for obj in objects]

        try:
            # Use shared utility to find sync groups
            sync_groups = find_sync_groups_s3(s3_keys, prefix=self.s3_prefix)
            logger.info(f"Found {len(sync_groups)} sync groups in S3")
            return sync_groups
        except ValueError as e:
            # Validation error (e.g., videos in non-leaf directory)
            logger.error(f"Invalid S3 directory structure: {e}")
            QMessageBox.critical(
                None,
                "Invalid S3 Directory Structure",
                f"Error scanning S3 directory structure:\n\n{e}\n\n"
                "Videos must be in leaf directories (directories with no subdirectories)."
            )
            return []

    async def download_partial_videos(self, sync_groups: List[str]) -> bool:
        """
        Download first 20MB of each video to temp directory.

        Args:
            sync_groups: List of directory paths containing videos

        Returns:
            True if successful
        """
        # Create temp directory
        self.temp_dir = tempfile.mkdtemp(prefix="s3_sync_")
        logger.info(f"Created temp directory: {self.temp_dir}")

        # Get all S3 objects again to find video files in each sync group
        objects = await self.s3_manager.list_directory(self.s3_prefix)

        # Collect all video files to download
        download_tasks = []

        for sync_group in sync_groups:
            # Construct the full S3 prefix for this sync group
            if sync_group == ".":
                group_prefix = self.s3_prefix
            else:
                group_prefix = self.s3_prefix + sync_group + "/"

            # Find all video files in this sync group
            for obj in objects:
                key = obj['Key']

                # Check if this object is in the current sync group
                if key.startswith(group_prefix):
                    rel_path = key[len(group_prefix):]

                    # Only include direct children (not nested subdirectories)
                    if '/' not in rel_path and rel_path.lower().endswith(('.mov', '.mp4')):
                        # This is a video file in the sync group
                        local_rel_path = key[len(self.s3_prefix):] if key.startswith(self.s3_prefix) else key
                        # Strip leading slashes to ensure relative path
                        local_rel_path = local_rel_path.lstrip('/')
                        local_path = str(Path(self.temp_dir) / local_rel_path)
                        download_tasks.append((key, local_path))

        # Show progress dialog
        progress = QProgressDialog(
            "Downloading partial videos from S3 (30MB each)...",
            "Cancel",
            0,
            len(download_tasks)
        )
        progress.setWindowTitle("Downloading from S3")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()

        # Download in parallel
        successful = 0
        for i, (s3_key, local_path) in enumerate(download_tasks):
            if progress.wasCanceled():
                logger.info("Download cancelled by user")
                return False

            logger.info(f"Downloading {i+1}/{len(download_tasks)}: {s3_key}")

            success = await self.s3_manager.download_partial_video(s3_key, local_path)

            if success:
                successful += 1
                # Add to mapping
                self.temp_to_s3_mapping[local_path] = s3_key
            else:
                logger.warning(f"Failed to download {s3_key}")

            progress.setValue(i + 1)
            # Emit progress signal for setup widget
            self.download_progress.emit(i + 1, len(download_tasks))

        progress.close()

        logger.info(f"Downloaded {successful}/{len(download_tasks)} files successfully")
        return successful > 0

    def launch_sync_bench(self):
        """Launch SyncBench with partial videos"""
        logger.info("Launching SyncBench with partial videos")

        # Collect video paths from temp directory
        video_paths = self.collect_temp_video_paths()

        if not video_paths:
            QMessageBox.warning(
                None,
                "No Videos",
                "No videos found in temporary directory."
            )
            return

        # Get codec from settings
        codec = "av1" if self.settings.reencode_to_av1 else "h264"

        # Get max resolution
        max_resolution = RESOLUTION_DIMENSIONS.get(self.settings.max_video_resolution)
        if max_resolution is None:
            max_resolution = (1280, 720)

        # Create SyncBench instance
        # Note: parent=None because QMainWindow requires QWidget parent, not QObject
        self.sync_bench = SyncBench(
            paths=video_paths,
            output_dir=self.temp_dir,
            codec=codec,
            max_resolution=max_resolution,
            s3_mode=True,  # Skip video processing for S3 partial files
            parent=None
        )

        # Connect to sync completed signal
        self.sync_bench.videos_synced.connect(self.on_videos_synced)
        self.sync_bench.sync_cancelled.connect(self.on_sync_cancelled)

        # Show the window
        self.sync_bench.show()

    def collect_temp_video_paths(self) -> List[str]:
        """Collect video paths from temp directory using recursive scanning"""
        try:
            sync_groups = find_sync_groups_local(self.temp_dir, max_depth=3)
            paths = [str(group) for group in sync_groups]
            logger.info(f"Collected {len(paths)} sync groups from temp directory")
            return paths
        except ValueError as e:
            logger.error(f"Invalid temp directory structure: {e}")
            return []

    def on_videos_synced(self, synced_files: dict):
        """Handle SyncBench completion - generate and upload sync_info.json"""
        logger.info("Videos synced, generating sync_info.json")

        # Show confirmation dialog
        reply = QMessageBox.information(
            None,
            "Sync Complete",
            "Video sync points have been set.\n\n"
            "Since you're working with S3 videos, full processing cannot be done locally.\n\n"
            "A sync_info.json file will be generated and uploaded to S3 for cloud processing.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply != QMessageBox.StandardButton.Yes:
            logger.info("User cancelled sync_info generation")
            self.cleanup_temp_files()
            if self.job_id:
                self.abandon_job()
            self.workflow_cancelled.emit()
            return

        # Generate sync_info
        asyncio.create_task(self.generate_and_upload_sync_info())

    async def generate_and_upload_sync_info(self):
        """Generate sync_info.json and upload to S3"""
        try:
            # Get tracks and sync parameters from SyncBench
            tracks = self.sync_bench.tracks
            sync_params = SyncEngine.calculate_sync_parameters(tracks)

            if not sync_params:
                QMessageBox.warning(
                    None,
                    "Sync Data Missing",
                    "Could not generate sync info - sync points may not be set correctly."
                )
                return

            # Generate sync info
            sync_info = SyncInfoGenerator.generate(
                tracks=tracks,
                sync_params=sync_params,
                s3_bucket=self.s3_bucket,
                s3_prefix=self.s3_prefix,
                temp_dir_to_s3_mapping=self.temp_to_s3_mapping
            )

            # Upload to S3
            sync_info_key = f"{self.s3_prefix}/sync_info.json".replace("//", "/")
            success = await self.s3_manager.upload_json(sync_info.to_dict(), sync_info_key)

            if success:
                QMessageBox.information(
                    None,
                    "Success",
                    f"Sync info uploaded successfully!\n\n"
                    f"S3 location:\n"
                    f"s3://{self.s3_bucket}/{sync_info_key}\n\n"
                    f"Temporary files will be cleaned up."
                )
                # Close SyncBench window
                if self.sync_bench:
                    self.sync_bench.close()
                    self.sync_bench = None
                self.workflow_completed.emit(sync_info_key)
            else:
                QMessageBox.critical(
                    None,
                    "Upload Failed",
                    "Failed to upload sync_info.json to S3.\n\n"
                    "Check logs for details."
                )
                # Still close SyncBench even on upload failure
                if self.sync_bench:
                    self.sync_bench.close()
                    self.sync_bench = None

        except Exception as e:
            logger.error(f"Failed to generate/upload sync_info: {e}")
            QMessageBox.critical(
                None,
                "Error",
                f"Failed to generate sync info:\n{str(e)}"
            )
        finally:
            # Cleanup temp files
            self.cleanup_temp_files()

    def on_sync_cancelled(self):
        """Handle sync cancellation"""
        logger.info("Sync cancelled by user")

        # If this was an auto job, abandon it via API
        if self.job_id:
            self.abandon_job()

        self.cleanup_temp_files()
        self.workflow_cancelled.emit()

    def abandon_job(self):
        """Abandon the current job via API"""
        from services.video_job_service import VideoJobService
        import requests

        if not self.job_id:
            logger.warning("No job ID to abandon")
            return

        logger.info(f"Abandoning job {self.job_id}")

        try:
            success = VideoJobService.abandon_job(self.job_id)

            if success:
                logger.info(f"Job {self.job_id} abandoned successfully")
            else:
                logger.warning(f"Job {self.job_id} abandonment returned false")

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to abandon job {self.job_id}: {e}")
            # Don't show error to user - this is a background operation
        except Exception as e:
            logger.error(f"Unexpected error abandoning job: {e}")

        finally:
            # Clear the job ID
            self.job_id = None

    def cleanup_temp_files(self):
        """Delete temporary partial video files"""
        if self.temp_dir and Path(self.temp_dir).exists():
            try:
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temp directory: {self.temp_dir}")
            except Exception as e:
                logger.error(f"Failed to cleanup temp directory: {e}")
            finally:
                self.temp_dir = None
