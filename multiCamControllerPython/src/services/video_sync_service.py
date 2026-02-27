"""Video synchronization service for integrating video_syncer into multiCamController"""

import logging
from pathlib import Path
from typing import List, Optional, Dict
from PySide6.QtWidgets import QDialog
from PySide6.QtCore import Qt, Signal

from video_syncer.gui import SyncBench

logger = logging.getLogger(__name__)


class VideoSyncDialog(QDialog):
    """Dialog wrapper for SyncBench that can be used modally"""

    sync_completed = Signal(dict)  # Emits dict with synced file paths
    sync_cancelled = Signal()

    def __init__(self, video_paths: List[str], output_dir: Optional[str] = None, codec: str = "av1", max_resolution: Optional[tuple[int, int]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Video Synchronization")
        self.setModal(True)
        self.resize(1400, 900)

        # Store output directory
        self.output_dir = output_dir
        self.synced_files: Dict[str, str] = {}  # original -> synced mapping

        # Create SyncBench instance (uses existing QApplication)
        self.sync_bench = SyncBench(video_paths, output_dir=output_dir, codec=codec, max_resolution=max_resolution)

        # Connect to SyncBench completion signals
        if hasattr(self.sync_bench, 'videos_synced'):
            self.sync_bench.videos_synced.connect(self._on_videos_synced)
        if hasattr(self.sync_bench, 'sync_cancelled'):
            self.sync_bench.sync_cancelled.connect(self._on_sync_cancelled)

        # Set up layout
        from PySide6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.sync_bench)

    def _on_videos_synced(self, files_dict: Dict[str, str]):
        """Handle videos synced signal from SyncBench."""
        self.synced_files = files_dict
        self.accept()  # Close dialog with accepted status

    def _on_sync_cancelled(self):
        """Handle sync cancelled signal from SyncBench."""
        self.reject()  # Close dialog with rejected status

    def get_synced_files(self) -> Dict[str, str]:
        """
        Get mapping of original files to synced files.

        Returns:
            Dict mapping original file paths to synced file paths
        """
        # TODO: Implement proper file tracking from SyncBench
        # For now, this is a placeholder that returns the original files
        # We need to track what SyncBench outputs
        return self.synced_files

    def closeEvent(self, event):
        """Handle dialog close - emit appropriate signal"""
        # Check if sync was completed or cancelled
        # TODO: Add proper completion tracking
        synced_files = self.get_synced_files()

        if synced_files:
            self.sync_completed.emit(synced_files)
        else:
            self.sync_cancelled.emit()

        event.accept()


class VideoSyncService:
    """Service for synchronizing videos using the video_syncer UI"""

    @staticmethod
    async def sync_videos(
        video_paths: List[str],
        output_dir: Optional[str] = None,
        codec: str = "av1",
        max_resolution: Optional[tuple[int, int]] = None,
        parent_widget=None
    ) -> Optional[List[str]]:
        """
        Show video sync UI and wait for user to sync videos.

        Args:
            video_paths: List of video file paths to sync
            output_dir: Directory to save synced videos (optional)
            codec: Video codec to use ('av1' or 'h264')
            max_resolution: Maximum resolution tuple (width, height) or None for no limit
            parent_widget: Parent widget for the dialog

        Returns:
            List of synced video file paths, or None if cancelled
        """
        if not video_paths:
            logger.warning("No video paths provided for syncing")
            return None

        logger.info(f"Starting video sync UI with {len(video_paths)} videos, codec: {codec}, max_resolution: {max_resolution}")

        # Create and show sync dialog
        dialog = VideoSyncDialog(video_paths, output_dir, codec, max_resolution, parent_widget)

        # Store result
        result = None
        synced_files = []

        def on_sync_completed(files_dict):
            nonlocal result, synced_files
            if files_dict:
                synced_files = list(files_dict.values())
                result = synced_files
            else:
                # No synced files, use originals
                synced_files = video_paths
                result = video_paths
            logger.info(f"Sync completed with {len(synced_files)} files")

        def on_sync_cancelled():
            nonlocal result, synced_files
            # User cancelled, use original files
            synced_files = video_paths
            result = video_paths
            logger.info("Sync cancelled, using original files")

        # Connect signals
        dialog.sync_completed.connect(on_sync_completed)
        dialog.sync_cancelled.connect(on_sync_cancelled)

        # Show modal dialog (blocks until closed)
        dialog.exec()

        return result
