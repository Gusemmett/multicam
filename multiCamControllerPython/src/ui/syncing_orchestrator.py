"""Orchestrator for video syncing workflow"""

import logging
import asyncio
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox
from models.app_settings import AppSettings
from .syncing_setup_window import SyncingSetupWindow
from .s3_syncing_workflow import S3SyncingWorkflow
from utils.session_parser import find_sync_groups_local

logger = logging.getLogger(__name__)


class SyncingOrchestrator(QObject):
    """Manages the video syncing workflow from setup to execution"""

    # Signal emitted when syncing workflow is cancelled or completed
    workflow_cancelled = Signal()
    workflow_completed = Signal()

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setup_widget = None  # Reference to setup widget (owned by main window)
        self.sync_bench = None
        self.s3_workflow = None
        self.current_job_id = None  # Track current job ID for auto mode

    def set_setup_widget(self, setup_widget):
        """Set reference to the setup widget (called by main window)"""
        self.setup_widget = setup_widget

    def on_setup_complete(self, source_type: str, path: str, job_id: str):
        """Handle completion of setup wizard"""
        logger.info(f"Setup complete: source_type={source_type}, path={path}, job_id={job_id or 'none'}")

        # Store job_id if provided
        self.current_job_id = job_id if job_id else None

        if source_type == "local":
            self.start_local_workflow(path)
        elif source_type == "s3" or source_type == "auto":
            # Both S3 and auto use the same S3 workflow
            self.start_s3_workflow(path)
        else:
            logger.error(f"Unknown source type: {source_type}")

    def start_local_workflow(self, main_folder: str):
        """Start local folder syncing workflow"""
        logger.info(f"Starting local workflow: {main_folder}")

        # Save folder to settings for next time
        self.settings.last_video_sync_folder = main_folder
        self.settings.save()

        # Collect video paths
        video_paths = self.collect_video_paths(main_folder)

        if not video_paths:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                None,
                "No Videos Found",
                f"No video files were found in the selected folder:\n{main_folder}\n\n"
                "Please ensure the folder contains .mp4 video files or subdirectories with video files."
            )
            logger.warning(f"No videos found in {main_folder}")
            return

        logger.info(f"Found {len(video_paths)} video paths to load")

        # Launch SyncBench with collected paths
        self.launch_sync_bench(video_paths, main_folder)

    def collect_video_paths(self, main_folder: str) -> list[str]:
        """
        Collect video paths from the main folder using recursive scanning.

        Recursively scans directories (max depth 3) to find sync groups.
        A sync group is any directory containing video files (.mov/.mp4).
        All videos in a sync group are assumed to be synced together.

        Returns a list of directory paths, each containing one or more videos to sync.
        """
        try:
            sync_groups = find_sync_groups_local(main_folder, max_depth=3)
            paths = [str(group) for group in sync_groups]
            logger.info(f"Found {len(paths)} sync groups")
            return paths
        except ValueError as e:
            # Validation error (e.g., videos in non-leaf directory)
            logger.error(f"Invalid directory structure: {e}")
            QMessageBox.critical(
                None,
                "Invalid Directory Structure",
                f"Error scanning directory structure:\n\n{e}\n\n"
                "Videos must be in leaf directories (directories with no subdirectories)."
            )
            return []

    def launch_sync_bench(self, video_paths: list[str], output_dir: str):
        """Launch the SyncBench window with the selected video paths"""
        from video_syncer.gui.main_window import SyncBench
        from utils.constants import RESOLUTION_DIMENSIONS

        logger.info(f"Launching SyncBench with {len(video_paths)} paths")

        # Get codec from settings
        codec = "av1" if self.settings.reencode_to_av1 else "h264"

        # Get max resolution from settings using the RESOLUTION_DIMENSIONS mapping
        max_resolution = RESOLUTION_DIMENSIONS.get(self.settings.max_video_resolution)
        if max_resolution is None:
            # If "original" or invalid, default to 720p
            if self.settings.max_video_resolution != "original":
                logger.warning(f"Invalid resolution: {self.settings.max_video_resolution}, defaulting to 720p")
            max_resolution = (1280, 720)

        # Create SyncBench instance
        # Note: parent=None because QMainWindow requires QWidget parent, not QObject
        self.sync_bench = SyncBench(
            paths=video_paths,
            output_dir=output_dir,
            codec=codec,
            max_resolution=max_resolution,
            s3_mode=False,  # Local mode: process full videos
            parent=None
        )

        # Connect signals
        self.sync_bench.sync_cancelled.connect(self.on_sync_cancelled)
        self.sync_bench.videos_synced.connect(self.on_videos_synced)

        # Show the window
        self.sync_bench.show()

    def start_s3_workflow(self, s3_full_path: str):
        """Start S3 syncing workflow"""
        logger.info(f"Starting S3 workflow: {s3_full_path}")

        # Parse bucket and path from "bucket:path" format
        try:
            bucket, s3_path = s3_full_path.split(":", 1)
        except ValueError:
            logger.error(f"Invalid S3 path format: {s3_full_path}")
            QMessageBox.critical(
                None,
                "Invalid S3 Path",
                f"Invalid S3 path format: {s3_full_path}\n\n"
                "Expected format: bucket:path"
            )
            return

        # Save S3 URI to settings for next time (reconstruct full URI)
        s3_uri = f"s3://{bucket}/{s3_path}" if s3_path else f"s3://{bucket}"
        self.settings.last_s3_sync_path = s3_uri
        self.settings.save()

        # Create S3 workflow with self as parent
        self.s3_workflow = S3SyncingWorkflow(self.settings, parent=self)
        self.s3_workflow.workflow_completed.connect(self.on_s3_workflow_completed)
        self.s3_workflow.workflow_cancelled.connect(self.on_sync_cancelled)

        # Connect download progress to setup widget
        if self.setup_widget:
            self.s3_workflow.download_progress.connect(self.setup_widget.show_progress)

        # Start the workflow (async) with optional job_id
        asyncio.create_task(self.s3_workflow.start_workflow(bucket, s3_path, self.current_job_id))

    def on_sync_cancelled(self):
        """Handle syncing cancellation"""
        logger.info("Video syncing cancelled")
        self.workflow_cancelled.emit()

    def on_videos_synced(self, synced_files: dict):
        """Handle successful video syncing"""
        logger.info(f"Videos synced successfully: {len(synced_files)} files")
        # Close SyncBench window
        if self.sync_bench:
            self.sync_bench.close()
            self.sync_bench = None
        # Emit completion
        self.workflow_completed.emit()

    def on_s3_workflow_completed(self, sync_info_key: str):
        """Handle S3 workflow completion"""
        logger.info(f"S3 workflow completed: {sync_info_key}")

        # If this was an auto job, complete the job via API
        if self.current_job_id:
            self.complete_job(sync_info_key)

        # Emit completion
        self.workflow_completed.emit()

    def complete_job(self, sync_info_key: str):
        """Complete the current job via API"""
        from services.video_job_service import VideoJobService
        import requests

        if not self.current_job_id:
            logger.warning("No job ID to complete")
            return

        logger.info(f"Completing job {self.current_job_id}")

        try:
            # Prepare metadata
            metadata = {
                "sync_info_key": sync_info_key,
                "processor": "multiCamController"
            }

            # Complete the job
            success = VideoJobService.complete_job(self.current_job_id, metadata)

            if success:
                logger.info(f"Job {self.current_job_id} completed successfully")
            else:
                logger.warning(f"Job {self.current_job_id} completion returned false")

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to complete job {self.current_job_id}: {e}")
            QMessageBox.warning(
                None,
                "Job Completion Failed",
                f"The syncing was successful, but failed to mark the job as complete:\n\n{str(e)}\n\n"
                f"The job may expire and be reassigned to another worker."
            )
        except Exception as e:
            logger.error(f"Unexpected error completing job: {e}")

        finally:
            # Clear the current job ID
            self.current_job_id = None
